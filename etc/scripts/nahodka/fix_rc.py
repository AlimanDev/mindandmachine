from django.db.models import Q, Exists, OuterRef
from django.db.models.functions import Length
from src.apps.base.models import Employment, Employee, User
from src.apps.integration.models import UserExternalCode
from src.apps.recognition.models import Tick
from src.apps.timetable.models import WorkerDay, AttendanceRecords
from src.apps.timetable.timesheet.tasks import calc_timesheets
from src.apps.timetable.worker_day.tasks import recalc_work_hours
UserExternalCode.objects.filter(user_id=179).delete()  # РЦ user_id 179 -- Галиев
User.objects.filter(~Exists(Employment.objects.filter(employee__user_id=OuterRef('id')))).delete()
wdays_qs = WorkerDay.objects.annotate(tn_len=Length('employee__tabel_code')).filter(tn_len=10).select_related(
    'employee__user', 'employment__employee__user')
employments_set_ids = set()
for wd in wdays_qs:
    new_employee = Employee.objects.annotate(tn_len=Length('tabel_code')).filter(
        ~Q(id=wd.employee_id),
        user__last_name=wd.employee.user.last_name,
        user__first_name=wd.employee.user.first_name,
        user__middle_name=wd.employee.user.middle_name,
        tn_len=36,
    ).first()
    new_employment = Employment.objects.get_active(
        dt_from=wd.dt,
        dt_to=wd.dt
    ).annotate(tn_len=Length('employee__tabel_code')).filter(
        ~Q(employee_id=wd.employee_id),
        employee__user__last_name=wd.employee.user.last_name,
        employee__user__first_name=wd.employee.user.first_name,
        employee__user__middle_name=wd.employee.user.middle_name,
        tn_len=36,
    ).first()
    if new_employee and new_employment:
        employments_set_ids.add(wd.employment_id)
        print(wd.employee, new_employee)
        print(wd.employment, new_employment)
        wd.employee = new_employee
        wd.employment = new_employment
        wd.save()
for tick in Tick.objects.annotate(tn_len=Length('employee__tabel_code')).filter(tn_len=10).select_related(
        'employee__user'):
    new_employee = Employee.objects.annotate(tn_len=Length('tabel_code')).filter(
        ~Q(id=tick.employee_id),
        user__last_name=tick.employee.user.last_name,
        user__first_name=tick.employee.user.first_name,
        user__middle_name=tick.employee.user.middle_name,
        tn_len=36,
    ).first()
    if new_employee:
        tick.employee_id = new_employee
        tick.user_id = new_employee.user_id
        tick.save()
for att_record in AttendanceRecords.objects.annotate(tn_len=Length('employee__tabel_code')).filter(
        tn_len=10).select_related('employee__user'):
    new_employee = Employee.objects.annotate(tn_len=Length('tabel_code')).filter(
        ~Q(id=att_record.employee_id),
        user__last_name=att_record.employee.user.last_name,
        user__first_name=att_record.employee.user.first_name,
        user__middle_name=att_record.employee.user.middle_name,
        tn_len=36,
    ).first()
    if new_employee:
        att_record.employee_id = new_employee
        att_record.user_id = new_employee.user_id
        att_record.save()
if employments_set_ids:
    Employment.objects.filter(id__in=employments_set_ids).delete()
users_to_delete = User.objects.filter(~Exists(Employment.objects.filter(employee__user_id=OuterRef('id'))))
user_codes_to_delete = UserExternalCode.objects.filter(user__in=users_to_delete).select_related('user')
print(user_codes_to_delete)
user_codes_to_delete.delete()
# РЦ Марсель, Садыков, 1555, 05717766996
Tick.objects.filter(employee_id=1585, user_id=1555).update(employee_id=1931, user_id=1888)
AttendanceRecords.objects.filter(employee_id=1585, user_id=1555).update(employee_id=1931, user_id=1888)
WorkerDay.objects.filter(employee_id=1585).update(employee_id=1931)
Employment.objects.filter(employee_id=1585).update(employee_id=1931)
UserExternalCode.objects.filter(user_id=1555).delete()
User.objects.filter(id=1555).delete()
print(users_to_delete.delete())
from etc.scripts.shift_schedule import load_shift_schedule, load_shift_schedule_intervals
from datetime import date
load_shift_schedule('/home/wonder/Downloads/Telegram Desktop/РЦ_графики 20211101-2.xlsx', from_dt=date(2021, 11, 1))
load_shift_schedule_intervals('/home/wonder/Downloads/Telegram Desktop/РЦ_графики_сотрудников_интервальный_2.xlsx')
# load_shift_schedule('/home/wonder/Downloads/Telegram Desktop/АТЛ_графики 20211101-2.xlsx', from_dt=date(2021, 11, 1))
# load_shift_schedule_intervals('/home/wonder/Downloads/Telegram Desktop/АТЛ_графики_сотрудников_интервальный_2.xlsx')
recalc_work_hours(dt__gte='2021-11-01', dt__lte='2021-12-31', type__is_dayoff=False)
calc_timesheets(dt_from='2021-11-01', dt_to='2021-11-30')
calc_timesheets(dt_from='2021-12-01', dt_to='2021-12-31')
