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
    def _get_batch_delete_others_scope(cls):
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
    def _batch_update_or_create_rel_objs(cls, rel_objs_data, objs, rel_objs_mapping):
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
            # TODO: удаление других объектов по _rel_obj_reverse_fk_field ?
            rel_obj_cls.batch_update_or_create(data=rel_obj_data_list, delete_others_scope=[rel_obj_reverse_fk_field])

    @classmethod
    def batch_update_or_create(cls, data: list, update_key_field: str = 'id', delete_others_scope: list = None):
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
            delete_others_scope: список полей, по которым будет определяться какие объекты будут удалены
                после массового создания/обновления (если None, то удалены не будут)

        # TODO: Обновление связанных fk объектов?
        # TODO: Оптимистичный лок? Версия объектов? Пример: изменяем один и тот же WorkerDay в разных вкладках,
            должна быть ошибка если объект был изменен?
        # TODO: Проверка доступа к созданию/обновлению объектов (в т.ч. связанных)?
        # TODO: Настройка, которая определяет сколько объектов может быть создано в рамках delete_others_scope?
        # TODO: Проверки в рамках транзакции (настраиваемые для моделей), например проверка пересечения времени в WorkerDay для 1 пользователя
        # TODO: Сигналы для post/pre bulk_update и bulk_create ?
        """
        allowed_update_key_fields = cls._get_allowed_update_key_fields()
        if update_key_field not in allowed_update_key_fields:
            raise BatchUpdateOrCreateException(
                f'Not allowed update key field: "{update_key_field}", allowed fields: {allowed_update_key_fields}')

        with transaction.atomic():
            delete_others_scope = delete_others_scope or cls._get_batch_delete_others_scope()
            delete_others_set = set()
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

                if delete_others_scope:
                    for obj_to_create in objs_to_create:
                        delete_others_tuple = tuple((k, getattr(obj_to_create, k)) for k in delete_others_scope)
                        delete_others_set.add(delete_others_tuple)

                cls._batch_update_or_create_rel_objs(
                    rel_objs_data=rel_objs_data, objs=objs_to_create, rel_objs_mapping=rel_objs_mapping)

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

                if delete_others_scope:
                    for obj_to_update in objs_to_update:
                        delete_others_tuple = tuple((k, getattr(obj_to_update, k)) for k in delete_others_scope)
                        delete_others_set.add(delete_others_tuple)

                cls._batch_update_or_create_rel_objs(
                    rel_objs_data=rel_objs_data, objs=objs_to_update, rel_objs_mapping=rel_objs_mapping)

            objs = objs_to_create + objs_to_update

            if delete_others_set:
                q_for_delete = Q()
                for delete_others_tuples in delete_others_set:
                    q_for_delete |= Q(**dict(delete_others_tuples))

                cls.objects.filter(q_for_delete).exclude(id__in=list(obj.id for obj in objs)).delete()

        return objs

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
