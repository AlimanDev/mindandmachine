import io
from datetime import date, datetime

import pandas as pd
from django.core.exceptions import FieldDoesNotExist
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from src.notifications.helpers import send_mass_html_mail
from src.reports.helpers import get_datatuple
from src.util.commons import obj_deep_get


class DryRunRevertException(Exception):
    pass


class BatchUpdateOrCreateException(Exception):
    pass


class BatchUpdateOrCreateModelMixin:
    @classmethod
    def _get_batch_create_extra_kwargs(cls):
        return {}

    @classmethod
    def _get_rel_objs_mapping(cls):
        return {}

    @classmethod
    def _get_batch_update_select_related_fields(cls):
        return []

    @classmethod
    def _get_batch_delete_scope_fields_list(cls):
        raise NotImplementedError

    @classmethod
    def _get_allowed_update_key_fields(cls):
        l = ['id']
        if cls._is_field_exist('code'):
            l.append('code')
        return l

    @classmethod
    def _get_batch_update_or_create_transaction_checks_kwargs(cls, **kwargs):
        return {}

    @classmethod
    def _run_batch_update_or_create_transaction_checks(cls, **kwargs):
        pass

    @classmethod
    def _check_delete_qs_perm(cls, user, delete_qs, **kwargs):
        """
        Првоерка прав на удаление объектов на основе qs
            (для объектов, которые удаляем -- можем использовать qs)
        """
        pass

    @classmethod
    def _check_create_single_obj_perm(cls, user, obj_data, **extra_kwargs):
        pass

    @classmethod
    def _check_update_single_obj_perm(cls, user, existing_obj, obj_data, **extra_kwargs):
        pass

    @classmethod
    def _check_delete_single_obj_perm(cls, user, existing_obj=None, obj_id=None, **extra_kwargs):
        pass

    @classmethod
    def _check_delete_single_wd_data_perm(cls, user, obj_data, **extra_kwargs):
        pass

    @classmethod
    def _get_check_perms_extra_kwargs(cls, user=None):
        return {}

    @classmethod
    def _pop_rel_objs_data(cls, objs_data, rel_objs_mapping):
        rel_objs_to_create_or_update = {}
        for rel_obj_key in rel_objs_mapping.keys():
            # надежно ли по индексу делать сопоставление связанных объектов
            # (по id не можем, т.к. при создании объектов id еще нету, а нам нужно вытащить данные связанных объектов еще до создания)
            for idx, obj_dict in enumerate(objs_data):
                if rel_obj_key in obj_dict:
                    rel_obj_data = obj_dict.pop(rel_obj_key)
                    rel_objs_to_create_or_update.setdefault(idx, {}).setdefault(rel_obj_key, []).extend(rel_obj_data)
        return rel_objs_to_create_or_update

    @classmethod
    def _batch_update_or_create_rel_objs(cls, rel_objs_data, objs, rel_objs_mapping, stats, update_key_field):
        all_rel_objs_mapped_by_type = {}
        delete_scope_values_list_by_type = {}
        for idx, rel_objs_to_create_or_update in rel_objs_data.items():
            obj = objs[idx]
            for rel_obj_key, rel_obj_data_list in rel_objs_to_create_or_update.items():
                _rel_obj_cls, rel_obj_reverse_fk_field = rel_objs_mapping.get(rel_obj_key)
                for rel_obj_dict in rel_obj_data_list:
                    rel_obj_dict[
                        rel_obj_reverse_fk_field] = obj.pk
                all_rel_objs_mapped_by_type.setdefault(rel_obj_key, []).extend(rel_obj_data_list)
                delete_scope_values_list_by_type.setdefault(rel_obj_key, []).append({rel_obj_reverse_fk_field: obj.pk})

        for rel_obj_key, rel_obj_data_list in all_rel_objs_mapped_by_type.items():
            rel_obj_cls, rel_obj_reverse_fk_field = rel_objs_mapping.get(rel_obj_key)
            delete_scope_values_list = delete_scope_values_list_by_type.get(rel_obj_key)
            rel_obj_cls.batch_update_or_create(
                data=rel_obj_data_list, update_key_field=update_key_field,
                delete_scope_fields_list=[rel_obj_reverse_fk_field],
                delete_scope_values_list=delete_scope_values_list, stats=stats)

    @classmethod
    def _is_field_exist(cls, field_name):
        try:
            cls._meta.get_field(field_name)
        except FieldDoesNotExist:
            return False

        return True

    @classmethod
    def _batch_update_extra_handler(cls, obj):
        pass

    @classmethod
    def _get_batch_delete_manager(cls, ):
        if hasattr(cls, 'objects_with_excluded'):
            return cls.objects_with_excluded
        return cls.objects

    @classmethod
    def _get_diff_lookup_fields(cls):
        return []

    @classmethod
    def _get_diff_headers(cls):
        pass

    @classmethod
    def _get_diff_report_subject_fmt(cls):
        pass

    @classmethod
    def _get_skip_update_equality_fields(cls):
        return []

    @classmethod
    def _create_and_send_diff_report(cls, diff_report_email_to, diff_data, diff_headers, now):
        from src.util.models_converter import Converter
        created_df = pd.DataFrame(diff_data.get('created', []), dtype=str, columns=diff_headers)
        before_update_df = pd.DataFrame(diff_data.get('before_update', []), dtype=str, columns=diff_headers)
        after_update_df = pd.DataFrame(diff_data.get('after_update', []), dtype=str, columns=diff_headers)
        deleted_df = pd.DataFrame(diff_data.get('deleted', []), dtype=str, columns=diff_headers)
        skipped_df = pd.DataFrame(diff_data.get('skipped', []), dtype=str, columns=diff_headers)
        output = io.BytesIO()
        writer = pd.ExcelWriter(output, engine='xlsxwriter')
        created_df.to_excel(writer, index=False, sheet_name='Создано')
        before_update_df.to_excel(writer, index=False, sheet_name='До изменений')
        after_update_df.to_excel(writer, index=False, sheet_name='После изменений')
        deleted_df.to_excel(writer, index=False, sheet_name='Удалено')
        skipped_df.to_excel(writer, index=False, sheet_name='Пропущено')
        for sheet_name, df in [('Создано', created_df),
                               ('До изменений', before_update_df),
                               ('После изменений', after_update_df),
                               ('Удалено', deleted_df),
                               ('Пропущено', skipped_df)]:
            worksheet = writer.sheets[sheet_name]
            for idx, col in enumerate(df):  # loop through all columns
                worksheet.set_column(idx, idx, len(col) + 2)
        writer.save()
        subject = cls._get_diff_report_subject_fmt()
        datatuple = get_datatuple(
            diff_report_email_to,
            (subject or 'Отчет для сверки данных от {dttm_now}').format(dttm_now=Converter.convert_datetime(now)),
            f'Создано: {len(created_df.index)}, Удалено: {len(deleted_df.index)}, '
            f'Изменено: {len(after_update_df.index)}, Пропущено: {len(skipped_df.index)}',
            {
                'name': 'diff_report.xlsx',
                'file': output,
            },
        )
        send_mass_html_mail(datatuple)

    @classmethod
    def _pre_batch(cls, **kwargs):
        """
        Функция, которая будет вызвана перед созданием/удалением/изменением объектов
        """
        pass

    @classmethod
    def _post_batch(cls, **kwargs):
        """
        Функция, которая будет вызвана после выполнения метода batch_update_or_create
        """
        pass

    @classmethod
    def batch_update_or_create(
            cls, data: list, update_key_field: str = 'id', delete_scope_fields_list: list = None,
            delete_scope_values_list: list = None, delete_scope_filters: dict = None, stats=None, user=None,
            dry_run=False, diff_report_email_to: list = None, check_perms_extra_kwargs=None,
            generate_delete_scope_values=True, model_options=None):
        """
        Функция для массового создания и/или обновления объектов

        Нужно использовать с осторожностью, т.к.
            не будут срабатывать сигналы сохранения объектов
            нет валидации данных (предполагается, что валидация данных будет произведена до попадания в эту функцию,
                например, на уровне сериализатора drf)
            не будет запущен save для каждого объекта
            есть особенности при создании/обновления/удалении связанных объектов
            невозможно частично создать/обновить (если упадет ошибка хотя бы в 1 объекте, то откатится вся транзакция)
                # TODO: возможность опционально задать создавать/обновлять объекты через bulk
                    или поштучно с сбором ошибок при сохранении объектов?
        В чем плюсы:
            скорость выполнения
                (количество запросов к бд не растет с увеличением числа создаваемых/обновляемых/удаляемых объектов)
            единый интерфейс для всех объектов при массовом создании/обновлении объектов
            можно использовать существующие сериализаторы drf для валидации данных

        Параметры:
            data: список словарей объектов, которые будут созданы/обновлены
            update_key_field: уникальный ключ по которому будут синхронизированы объекты
                если в словаре значение по этому ключу None, то будет создан новый объект.
                если в словаре значение по этому ключу найдено среди существующих, то объект будет обновлен
                если в словаре значение по этому ключу не найдено среди существующих, то объект будет создан
                    # TODO: сейчас так? -- нужен тест
            delete_scope_fields_list: список полей, по которым будет определяться какие объекты будут удалены
                после массового создания/обновления (если None, то удалены не будут)
            delete_scope_values_list: список словарей с значениями для полей из delete_scope_fields_list,
                по которым будут определяться объекты, которые будут удалены
            user: пользователь, который инициировал вызов функции, используется для проверки прав доступа
                если None, то проверки доступа не производятся (считаем, что запуск производится системой)

        # TODO: Обновление связанных fk объектов?
        # TODO: Оптимистичный лок? Версия объектов? Пример: изменяем один и тот же WorkerDay в разных вкладках,
            должна быть ошибка если объект был изменен?
        # TODO: Настройка, которая определяет сколько объектов может быть создано в рамках delete_scope_fields_list? -- ???
        # TODO: Сигналы post_batch_update, post_batch_create ?
        """
        allowed_update_key_fields = cls._get_allowed_update_key_fields()
        if update_key_field not in allowed_update_key_fields:
            if allowed_update_key_fields:
                # костыль, чтобы брался id как ключ, вместо code для вложенных объектов
                update_key_field = allowed_update_key_fields[0]
            else:
                raise BatchUpdateOrCreateException(
                    f'Not allowed update key field: "{update_key_field}"')

        try:
            with transaction.atomic():
                diff_data = {}
                diff_lookup_fields = cls._get_diff_lookup_fields()
                diff_obj_keys = tuple(lookup_field.split('__') for lookup_field in diff_lookup_fields)
                diff_headers = cls._get_diff_headers()
                check_perms_extra_kwargs = check_perms_extra_kwargs or {}
                if user:
                    check_perms_extra_kwargs.update(cls._get_check_perms_extra_kwargs(user=user))
                stats = stats if stats is not None else {}
                delete_scope_fields_list = delete_scope_fields_list \
                    if delete_scope_fields_list is not None \
                    else cls._get_batch_delete_scope_fields_list()
                model_options = model_options or {}
                delete_scope_values_set = set()
                if delete_scope_values_list:
                    for delete_scope_values in delete_scope_values_list:
                        delete_scope_values_list_of_tuples = []
                        for delete_scope_field in delete_scope_fields_list:
                            value = delete_scope_values.get(delete_scope_field)
                            if isinstance(value, list):
                                value = tuple(value)
                            delete_scope_values_list_of_tuples.append((delete_scope_field, value))
                        delete_scope_values_set.add(tuple(delete_scope_values_list_of_tuples))
                to_skip = []
                to_create = []
                to_update_dict = {}
                update_keys = []
                objs_to_create = []
                objs_to_skip = []
                objs_to_update = []
                rel_objs_mapping = cls._get_rel_objs_mapping()
                now = timezone.now()
                for obj_dict in data:
                    keys_to_delete = [k for k in (obj_dict.keys()) if not cls._is_field_exist(k)]
                    for k in keys_to_delete:
                        del obj_dict[k]

                    update_key = obj_dict.get(update_key_field)
                    if update_key is None:
                        to_create.append(obj_dict)
                        if user and not check_perms_extra_kwargs.get('grouped_checks'):
                            cls._check_create_single_obj_perm(user, obj_dict, **check_perms_extra_kwargs)
                    else:
                        update_keys.append(update_key)
                        to_update_dict[update_key] = obj_dict

                filter_kwargs = {}
                if update_keys:
                    filter_kwargs[f"{update_key_field}__in"] = update_keys
                if delete_scope_filters:
                    filter_kwargs.update(delete_scope_filters)
                if filter_kwargs:
                    update_qs = cls.objects.filter(**filter_kwargs).select_related(
                        *cls._get_batch_update_select_related_fields())
                else:
                    update_qs = cls.objects.none()
                existing_objs = {
                    getattr(obj, update_key_field): obj for obj in update_qs
                }
                skip_update_equality_fields = cls._get_skip_update_equality_fields()
                for update_key in update_keys:
                    update_obj_dict = to_update_dict[update_key]
                    if update_key not in existing_objs:
                        update_obj_dict['dttm_modified'] = now
                        obj_to_create = to_update_dict.pop(update_key)
                        to_create.append(obj_to_create)
                        if user and not check_perms_extra_kwargs.get('grouped_checks'):
                            cls._check_create_single_obj_perm(user, obj_dict, **check_perms_extra_kwargs)
                    else:
                        existing_obj = existing_objs.get(update_key)
                        need_to_skip = True
                        for k, v in update_obj_dict.items():
                            if k not in rel_objs_mapping and k not in skip_update_equality_fields:
                                existing_obj_k_value = getattr(existing_obj, k)
                                is_equal = existing_obj_k_value == v
                                if not is_equal:
                                    need_to_skip = False
                                    break
                        if need_to_skip:
                            to_skip.append(to_update_dict.pop(update_key))
                            obj_to_skip = existing_objs.pop(update_key)
                            objs_to_skip.append(obj_to_skip)
                            diff_data.setdefault('skipped', []).append(
                                tuple(obj_deep_get(obj_to_skip, *keys) for keys in diff_obj_keys))
                        else:
                            update_obj_dict['dttm_modified'] = now
                            if user:
                                cls._check_update_single_obj_perm(
                                    user, existing_obj, obj_dict, **check_perms_extra_kwargs)

                if to_skip:
                    skip_rel_objs_data = cls._pop_rel_objs_data(
                        objs_data=to_skip, rel_objs_mapping=rel_objs_mapping)

                if to_create:
                    create_rel_objs_data = cls._pop_rel_objs_data(
                        objs_data=to_create, rel_objs_mapping=rel_objs_mapping)
                    objs_to_create = []
                    for obj_dict in to_create:
                        obj_to_create = cls(**obj_dict, **cls._get_batch_create_extra_kwargs())
                        objs_to_create.append(obj_to_create)
                        diff_data.setdefault('created', []).append(
                            tuple(obj_deep_get(obj_to_create, *keys) for keys in diff_obj_keys))

                update_fields_set = {"dttm_modified"}
                if to_update_dict:
                    to_update = list(to_update_dict.values())
                    update_rel_objs_data = cls._pop_rel_objs_data(
                        objs_data=to_update, rel_objs_mapping=rel_objs_mapping)
                    for update_dict in to_update:
                        update_key = update_dict.get(update_key_field)
                        obj = existing_objs.get(update_key)
                        diff_data.setdefault('before_update', []).append(
                            tuple(obj_deep_get(obj, *keys) for keys in diff_obj_keys))
                        for k, v in update_dict.items():
                            setattr(obj, k, v)
                            update_fields_set.add(k)
                        extra_update_fields = cls._batch_update_extra_handler(obj)
                        if extra_update_fields:
                            update_fields_set.update(extra_update_fields)
                        objs_to_update.append(obj)
                        diff_data.setdefault('after_update', []).append(
                            tuple(obj_deep_get(obj, *keys) for keys in diff_obj_keys))

                objs = objs_to_create + objs_to_update + objs_to_skip

                deleted_dict = {}
                objs_to_delete = []
                q_for_delete = Q()

                if delete_scope_fields_list or delete_scope_filters:
                    if not delete_scope_values_list and generate_delete_scope_values:
                        for obj_to_update in objs_to_update:
                            delete_scope_values_tuple = tuple(
                                (k, getattr(obj_to_update, k)) for k in delete_scope_fields_list if
                                hasattr(obj_to_update, k))
                            if delete_scope_values_tuple:
                                delete_scope_values_set.add(delete_scope_values_tuple)

                        for obj_to_create in objs_to_create:
                            delete_scope_values_tuple = tuple(
                                (k, getattr(obj_to_create, k)) for k in delete_scope_fields_list if
                                hasattr(obj_to_create, k))
                            if delete_scope_values_tuple:
                                delete_scope_values_set.add(delete_scope_values_tuple)

                        for obj_to_skip in objs_to_skip:
                            delete_scope_values_tuple = tuple(
                                (k, getattr(obj_to_skip, k)) for k in delete_scope_fields_list if
                                hasattr(obj_to_skip, k))
                            if delete_scope_values_tuple:
                                delete_scope_values_set.add(delete_scope_values_tuple)

                    if delete_scope_values_set or (
                            (not generate_delete_scope_values or not delete_scope_fields_list) and delete_scope_filters):
                        for delete_scope_values_tuples in delete_scope_values_set:
                            q_for_delete |= Q(**dict(delete_scope_values_tuples))

                        delete_manager = cls._get_batch_delete_manager()
                        delete_filter_kwargs = {}
                        if delete_scope_filters:
                            delete_filter_kwargs.update(delete_scope_filters)
                        delete_qs = delete_manager.filter(
                            q_for_delete, **delete_filter_kwargs).exclude(id__in=list(obj.id for obj in objs if obj.id))
                        if user and not check_perms_extra_kwargs.get('grouped_checks'):
                            cls._check_delete_qs_perm(user, delete_qs, **check_perms_extra_kwargs)
                        objs_to_delete = list(delete_qs)
                        for obj_to_delete in objs_to_delete:
                            diff_data.setdefault('deleted', []).append(
                                tuple(obj_deep_get(obj_to_delete, *keys) for keys in diff_obj_keys))

                cls._pre_batch(user=user, diff_data=diff_data, check_perms_extra_kwargs=check_perms_extra_kwargs)

                if objs_to_delete:
                    _total_deleted_count, deleted_dict = delete_qs.delete()

                if objs_to_skip:
                    cls._batch_update_or_create_rel_objs(
                        rel_objs_data=skip_rel_objs_data, objs=objs_to_skip, rel_objs_mapping=rel_objs_mapping,
                        stats=stats, update_key_field=update_key_field)

                if objs_to_create:
                    cls.objects.bulk_create(objs_to_create)  # в объектах будут проставлены id (только в postgres)
                    cls._batch_update_or_create_rel_objs(
                        rel_objs_data=create_rel_objs_data, objs=objs_to_create, rel_objs_mapping=rel_objs_mapping,
                        stats=stats, update_key_field=update_key_field)

                if objs_to_update:
                    update_fields_set.discard(cls._meta.pk.name)
                    cls.objects.bulk_update(objs_to_update, fields=update_fields_set)
                    cls._batch_update_or_create_rel_objs(
                        rel_objs_data=update_rel_objs_data, objs=objs_to_update, rel_objs_mapping=rel_objs_mapping,
                        stats=stats, update_key_field=update_key_field)

                cls_name = cls.__name__
                cls_stats = stats.setdefault(cls_name, {})
                if objs_to_create:
                    cls_stats['created'] = cls_stats.get('created', 0) + len(objs_to_create)
                if objs_to_update:
                    cls_stats['updated'] = cls_stats.get('updated', 0) + len(objs_to_update)
                if objs_to_skip:
                    cls_stats['skipped'] = cls_stats.get('skipped', 0) + len(objs_to_skip)
                for original_deleted_cls_name, deleted_count in deleted_dict.items():
                    if deleted_count:
                        deleted_cls_name = original_deleted_cls_name.split('.')[1]
                        deleted_cls_stats = stats.setdefault(deleted_cls_name, {})
                        deleted_cls_stats['deleted'] = deleted_cls_stats.get('deleted', 0) + deleted_dict.get(
                            original_deleted_cls_name)

                if diff_report_email_to:
                    cls._create_and_send_diff_report(diff_report_email_to, diff_data, diff_headers, now)

                cls._post_batch(
                    created_objs=objs_to_create, updated_objs=objs_to_update, deleted_objs=objs_to_delete,
                    diff_data=diff_data, stats=stats, model_options=model_options,
                    delete_scope_filters=delete_scope_filters, user=user,
                )

                transaction_checks_kwargs = cls._get_batch_update_or_create_transaction_checks_kwargs(
                    data=data, q_for_delete=q_for_delete, user=user)
                cls._run_batch_update_or_create_transaction_checks(**transaction_checks_kwargs)

                if dry_run:
                    raise DryRunRevertException()
        except DryRunRevertException:
            pass

        return objs, stats
