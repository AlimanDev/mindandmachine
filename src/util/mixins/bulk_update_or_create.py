from django.db import transaction
from django.db.models import Q
from django.utils import timezone


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
        return None

    @classmethod
    def _get_allowed_update_key_fields(cls):
        return ['id']

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
    def _batch_update_or_create_rel_objs(cls, rel_objs_data, objs, rel_objs_mapping, stats):
        all_rel_objs_mapped_by_type = {}
        for idx, rel_objs_to_create_or_update in rel_objs_data.items():
            obj = objs[idx]
            for rel_obj_key, rel_obj_data_list in rel_objs_to_create_or_update.items():
                _rel_obj_cls, rel_obj_reverse_fk_field = rel_objs_mapping.get(rel_obj_key)
                for rel_obj_dict in rel_obj_data_list:
                    rel_obj_dict[
                        rel_obj_reverse_fk_field] = obj.id  # нужна возможность указать другой ключ? (для всех вложенных, либо задавать в виде маппинга?)
                all_rel_objs_mapped_by_type.setdefault(rel_obj_key, []).extend(rel_obj_data_list)

        for rel_obj_key, rel_obj_data_list in all_rel_objs_mapped_by_type.items():
            rel_obj_cls, rel_obj_reverse_fk_field = rel_objs_mapping.get(rel_obj_key)
            rel_obj_cls.batch_update_or_create(
                data=rel_obj_data_list, delete_scope_fields_list=[rel_obj_reverse_fk_field], stats=stats)

    @classmethod
    def batch_update_or_create(
            cls, data: list, update_key_field: str = 'id', delete_scope_fields_list: list = None,
            delete_scope_values_list: list = None, stats=None):
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
            единый интерфейс для всех объектов при массовом создании/обновлении объектов
            можно использовать существующие сериализаторы drf для валидации данных

        Параметры:
            data: список словарей объектов, которые будут созданы/обновлены
            update_key_field: уникальный ключ по которому будут синхронизированы объекты
                если в словаре значение по этому ключу None, то будет создан новый объект.
                если в словаре значение по этому ключу найдено среди существующих, то объект будет обновлен
                если в словаре значение по этому ключу не найдено среди существующих, то объект будет создан
            delete_scope_fields_list: список полей, по которым будет определяться какие объекты будут удалены
                после массового создания/обновления (если None, то удалены не будут)
            delete_scope_values_list: список словарей с значениями для полей из delete_scope_fields_list,
                по которым будут определяться объекты, которые будут удалены

        # TODO: Обновление связанных fk объектов?
        # TODO: Оптимистичный лок? Версия объектов? Пример: изменяем один и тот же WorkerDay в разных вкладках,
            должна быть ошибка если объект был изменен?
        # TODO: Проверка доступа к созданию/обновлению объектов (в т.ч. связанных)?
        # TODO: Настройка, которая определяет сколько объектов может быть создано в рамках delete_scope_fields_list?
        # TODO: Проверки в рамках транзакции (настраиваемые для моделей), например проверка пересечения времени в WorkerDay для 1 пользователя
        # TODO: Сигналы для post/pre bulk_update и bulk_create ?
        """
        allowed_update_key_fields = cls._get_allowed_update_key_fields()
        if update_key_field not in allowed_update_key_fields:
            raise BatchUpdateOrCreateException(
                f'Not allowed update key field: "{update_key_field}", allowed fields: {allowed_update_key_fields}')

        with transaction.atomic():
            stats = stats or {}
            delete_scope_fields_list = delete_scope_fields_list or cls._get_batch_delete_scope_fields_list()
            delete_scope_values_set = set()
            if delete_scope_values_list:
                for delete_scope_values in delete_scope_values_list:
                    delete_scope_values_set.add(
                        tuple((delete_scope_field, delete_scope_values.get(delete_scope_field)) for delete_scope_field in
                            delete_scope_fields_list)
                    )
            to_create = []
            to_update = []
            update_keys = []
            objs_to_create = []
            objs_to_update = []
            rel_objs_mapping = cls._get_rel_objs_mapping()
            for obj_dict in data:
                update_key = obj_dict.get(update_key_field)
                if update_key is None:
                    to_create.append(obj_dict)
                else:
                    update_keys.append(update_key)
                    to_update.append(obj_dict)

            filter_kwargs = {
                f"{update_key_field}__in": update_keys,
            }
            existing_objs = {
                getattr(obj, update_key_field): obj
                for obj in cls.objects.filter(**filter_kwargs).select_related(
                    *cls._get_batch_update_select_related_fields())
            }

            if to_create:
                rel_objs_data = cls._pop_rel_objs_data(
                    objs_data=to_create, rel_objs_mapping=rel_objs_mapping)
                objs_to_create = [cls(**obj_dict, **cls._get_batch_create_extra_kwargs()) for obj_dict in to_create]
                cls.objects.bulk_create(objs_to_create)  # в объектах будут проставлены id (только в postgres)
                cls._batch_update_or_create_rel_objs(
                    rel_objs_data=rel_objs_data, objs=objs_to_create, rel_objs_mapping=rel_objs_mapping, stats=stats)

            update_fields = {"dttm_modified"}
            if to_update:
                rel_objs_data = cls._pop_rel_objs_data(
                    objs_data=to_update, rel_objs_mapping=rel_objs_mapping)
                for update_dict in to_update:
                    update_key = update_dict.get(update_key_field)
                    obj = existing_objs.get(update_key)
                    update_fields.update(set(f for f in update_dict.keys() if f != update_key_field))
                    obj.update(update_dict=update_dict, save=False)
                    objs_to_update.append(obj)
                cls.objects.bulk_update(objs_to_update, update_fields)
                cls._batch_update_or_create_rel_objs(
                    rel_objs_data=rel_objs_data, objs=objs_to_update, rel_objs_mapping=rel_objs_mapping, stats=stats)

            objs = objs_to_create + objs_to_update

            deleted_dict = {}
            if delete_scope_fields_list:
                for obj_to_update in objs_to_update:
                    delete_scope_values_tuple = tuple((k, getattr(obj_to_update, k)) for k in delete_scope_fields_list)
                    delete_scope_values_set.add(delete_scope_values_tuple)

                for obj_to_create in objs_to_create:
                    delete_scope_values_tuple = tuple((k, getattr(obj_to_create, k)) for k in delete_scope_fields_list)
                    delete_scope_values_set.add(delete_scope_values_tuple)

                if delete_scope_values_set:
                    q_for_delete = Q()
                    for delete_scope_values_tuples in delete_scope_values_set:
                        q_for_delete |= Q(**dict(delete_scope_values_tuples))

                    _total_deleted_count, deleted_dict = cls.objects.filter(
                        q_for_delete).exclude(id__in=list(obj.id for obj in objs)).delete()

            cls_name = cls.__name__
            cls_stats = stats.setdefault(cls_name, {})
            if objs_to_create:
                cls_stats['created'] = cls_stats.get('created', 0) + len(objs_to_create)
            if objs_to_update:
                cls_stats['updated'] = cls_stats.get('updated', 0) + len(objs_to_update)
            for original_deleted_cls_name, deleted_count in deleted_dict.items():
                if deleted_count:
                    deleted_cls_name = original_deleted_cls_name.split('.')[1]
                    deleted_cls_stats = stats.setdefault(deleted_cls_name, {})
                    deleted_cls_stats['deleted'] = deleted_cls_stats.get('deleted', 0) + deleted_dict.get(
                        original_deleted_cls_name)

        return objs, stats

    def update(self, update_dict=None, save=True, **kwargs):
        if not update_dict:
            update_dict = kwargs
        update_dict.update({'dttm_modified': timezone.now()})
        update_fields = {"dttm_modified"}
        for k, v in update_dict.items():
            setattr(self, k, v)
            update_fields.add(k)
        if save:
            self.save(update_fields=update_fields)
