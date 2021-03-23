from drf_yasg import openapi

shop_tree_response_schema_dict = {
    "200": openapi.Response(
        description="Returns shop tree",
        examples={
            "application/json": {
                "id": 1,
                "title": "string",
                "tm_open_dict": {"all": "07:00:00"},
                "tm_close_dict": {"all": "22:00:00"},
                "address": "string",
                "forecast_step_minutes": "01:00:00",
                "children": [
                    {
                        "id": 2,
                        "title": "string",
                        "tm_open_dict": {"all": "07:00:00"},
                        "tm_close_dict": {"all": "22:00:00"},
                        "address": "string",
                        "forecast_step_minutes": "01:00:00",
                        "children": [],
                    },
                    {
                        "id": 3,
                        "title": "string",
                        "tm_open_dict": {"0": "07:00:00", "1": "07:00:00", "2": "08:00:00", "3": "07:00:00", "4": "08:00:00", "5": "07:00:00", "6": "08:00:00"},
                        "tm_close_dict": {"0": "22:00:00", "1": "22:00:00", "2": "23:00:00", "3": "22:00:00", "4": "23:00:00", "5": "22:00:00", "6": "23:00:00"},
                        "address": "string",
                        "forecast_step_minutes": "01:00:00",
                        "children": [],
                    }
                ]
            }
        }
    )
}

# Description for efficieny
efficieny_response_schema_dict = {
    "200": openapi.Response(
        description="Returns efficiency",
        examples={
            "application/json": {
                "period_step": 60,
                "tt_periods": {
                    "real_cashiers": [
                        {
                            "dttm": "2020-09-01T00:00:00",
                            "amount": 0.0,
                        },
                        {
                            "dttm": "2020-09-01T01:00:00",
                            "amount": 0.0
                        }
                    ],
                    "predict_cashier_needs": [
                        {
                            "dttm": "2020-09-01T00:00:00",
                            "amount": 0.0
                        },
                        {
                            "dttm": "2020-09-01T01:00:00",
                            "amount": 0.0
                        },
                    ]
                },
                "day_stats": {
                    "covering": {
                        "2020-09-01": 0.0
                    },
                    "deadtime": {
                        "2020-09-01": 0.0
                    },
                    "predict_hours": {
                        "2020-09-01": 0.0
                    },
                    "graph_hours": {
                        "2020-09-01": 0.0
                    }
                },
                "lack_of_cashiers_on_period": [
                    {
                        "dttm": "2020-09-01T00:00:00",
                        "lack_of_cashiers": 0
                    },
                    {
                        "dttm": "2020-09-01T01:00:00",
                        "lack_of_cashiers": 0
                    },
                ],
            }
        }
    ),
}


worker_stat_response_schema_dictionary = {
    "200": openapi.Response(
        description="Returns worker stat",
        examples={
            "application/json": {
                "230": {
                    "fact": {
                        "approved": {
                            "paid_days": {
                                "total": 1,
                                "shop": 1,
                                "other": 0,
                                "overtime": 0,
                                "overtime_prev": -66
                            },
                            "paid_hours": {
                                "total": 11.0,
                                "shop": 11.0,
                                "other": 0,
                                "overtime": 3.0,
                                "overtime_prev": -528
                            }
                        },
                        "not_approved": {
                            "paid_days": {
                                "total": 0,
                                "shop": 0,
                                "other": 0,
                                "overtime": -1,
                                "overtime_prev": -66
                            },
                            "paid_hours": {
                                "total": 0,
                                "shop": 0,
                                "other": 0,
                                "overtime": -8,
                                "overtime_prev": -528
                            }
                        },
                        "combined": {
                            "paid_days": {
                                "total": 1,
                                "shop": 1,
                                "other": 0,
                                "overtime": 0,
                                "overtime_prev": -66
                            },
                            "paid_hours": {
                                "total": 11.0,
                                "shop": 11.0,
                                "other": 0,
                                "overtime": 3.0,
                                "overtime_prev": -528
                            }
                        }
                    },
                    "plan": {
                        "approved": {
                            "paid_days": {
                                "total": 1,
                                "shop": 1,
                                "other": 0,
                                "overtime": 0,
                                "overtime_prev": -66
                            },
                            "paid_hours": {
                                "total": 11.0,
                                "shop": 11.0,
                                "other": 0,
                                "overtime": 3.0,
                                "overtime_prev": -528
                            },
                            "day_type": {
                                "H": 0,
                                "W": 1,
                                "V": 0,
                                "TV": 0,
                                "S": 0,
                                "Q": 0,
                                "A": 0,
                                "M": 0,
                                "T": 0,
                                "O": 0,
                                "E": 0
                            }
                        },
                        "not_approved": {
                            "paid_days": {
                                "total": 0,
                                "shop": 0,
                                "other": 0,
                                "overtime": -1,
                                "overtime_prev": -66
                            },
                            "paid_hours": {
                                "total": 0,
                                "shop": 0,
                                "other": 0,
                                "overtime": -8,
                                "overtime_prev": -528
                            },
                            "day_type": {
                                "H": 0,
                                "W": 0,
                                "V": 0,
                                "TV": 0,
                                "S": 0,
                                "Q": 0,
                                "A": 0,
                                "M": 0,
                                "T": 0,
                                "O": 0,
                                "E": 0
                            }
                        },
                        "combined": {
                            "paid_days": {
                                "total": 1,
                                "shop": 1,
                                "other": 0,
                                "overtime": 0,
                                "overtime_prev": -66
                            },
                            "paid_hours": {
                                "total": 11.0,
                                "shop": 11.0,
                                "other": 0,
                                "overtime": 3.0,
                                "overtime_prev": -528
                            },
                            "day_type": {
                                "H": 0,
                                "W": 1,
                                "V": 0,
                                "TV": 0,
                                "S": 0,
                                "Q": 0,
                                "A": 0,
                                "M": 0,
                                "T": 0,
                                "O": 0,
                                "E": 0
                            }
                        }
                    }
                },
                "245": {
                    "fact": {
                        "approved": {
                            "paid_days": {
                                "total": 0,
                                "shop": 0,
                                "other": 0,
                                "overtime": -1,
                                "overtime_prev": -22
                            },
                            "paid_hours": {
                                "total": 0,
                                "shop": 0,
                                "other": 0,
                                "overtime": -8,
                                "overtime_prev": -176
                            }
                        },
                        "not_approved": {
                            "paid_days": {
                                "total": 0,
                                "shop": 0,
                                "other": 0,
                                "overtime": -1,
                                "overtime_prev": -22
                            },
                            "paid_hours": {
                                "total": 0,
                                "shop": 0,
                                "other": 0,
                                "overtime": -8,
                                "overtime_prev": -176
                            }
                        },
                        "combined": {
                            "paid_days": {
                                "total": 0,
                                "shop": 0,
                                "other": 0,
                                "overtime": -1,
                                "overtime_prev": -22
                            },
                            "paid_hours": {
                                "total": 0,
                                "shop": 0,
                                "other": 0,
                                "overtime": -8,
                                "overtime_prev": -176
                            }
                        }
                    },
                    "plan": {
                        "approved": {
                            "paid_days": {
                                "total": 0,
                                "shop": 0,
                                "other": 0,
                                "overtime": -1,
                                "overtime_prev": -22
                            },
                            "paid_hours": {
                                "total": 0,
                                "shop": 0,
                                "other": 0,
                                "overtime": -8,
                                "overtime_prev": -176
                            },
                            "day_type": {
                                "H": 1,
                                "W": 0,
                                "V": 0,
                                "TV": 0,
                                "S": 0,
                                "Q": 0,
                                "A": 0,
                                "M": 0,
                                "T": 0,
                                "O": 0,
                                "E": 0
                            }
                        },
                        "not_approved": {
                            "paid_days": {
                                "total": 0,
                                "shop": 0,
                                "other": 0,
                                "overtime": -1,
                                "overtime_prev": -22
                            },
                            "paid_hours": {
                                "total": 0,
                                "shop": 0,
                                "other": 0,
                                "overtime": -8,
                                "overtime_prev": -176
                            },
                            "day_type": {
                                "H": 0,
                                "W": 0,
                                "V": 0,
                                "TV": 0,
                                "S": 0,
                                "Q": 0,
                                "A": 0,
                                "M": 0,
                                "T": 0,
                                "O": 0,
                                "E": 0
                            }
                        },
                        "combined": {
                            "paid_days": {
                                "total": 0,
                                "shop": 0,
                                "other": 0,
                                "overtime": -1,
                                "overtime_prev": -22
                            },
                            "paid_hours": {
                                "total": 0,
                                "shop": 0,
                                "other": 0,
                                "overtime": -8,
                                "overtime_prev": -176
                            },
                            "day_type": {
                                "H": 1,
                                "W": 0,
                                "V": 0,
                                "TV": 0,
                                "S": 0,
                                "Q": 0,
                                "A": 0,
                                "M": 0,
                                "T": 0,
                                "O": 0,
                                "E": 0
                            }
                        }
                    }
                },
            }
        }
    ),
}

daily_stat_response_schema_dictionary = {
    "200": openapi.Response(
        description='Returns daily stat',
        examples={
            'application/json':{
                "2020-10-01": {
                    "plan": {
                        "approved": {
                            "shop": {
                                "shifts": 5,
                                "paid_hours": 35,
                                "fot": 0.0
                            },
                            "outsource": {
                                "shifts": 0,
                                "paid_hours": 0,
                                "fot": 0.0
                            },
                            "vacancies": {
                                "shifts": 0,
                                "paid_hours": 0,
                                "fot": 0.0
                            }
                        },
                        "not_approved": {
                            "shop": {
                                "shifts": 0,
                                "paid_hours": 0,
                                "fot": 0.0
                            },
                            "outsource": {
                                "shifts": 0,
                                "paid_hours": 0,
                                "fot": 0.0
                            },
                            "vacancies": {
                                "shifts": 0,
                                "paid_hours": 0,
                                "fot": 0.0
                            }
                        },
                        "combined": {
                            "shop": {
                                "shifts": 5,
                                "paid_hours": 35,
                                "fot": 0.0
                            },
                            "outsource": {
                                "shifts": 0,
                                "paid_hours": 0,
                                "fot": 0.0
                            },
                            "vacancies": {
                                "shifts": 0,
                                "paid_hours": 0,
                                "fot": 0.0
                            }
                        }
                    },
                    "fact": {
                        "approved": {
                            "shop": {
                                "shifts": 5,
                                "paid_hours": 44,
                                "fot": 0.0
                            },
                            "outsource": {
                                "shifts": 0,
                                "paid_hours": 0,
                                "fot": 0.0
                            },
                            "vacancies": {
                                "shifts": 0,
                                "paid_hours": 0,
                                "fot": 0.0
                            }
                        },
                        "not_approved": {
                            "shop": {
                                "shifts": 0,
                                "paid_hours": 0,
                                "fot": 0.0
                            },
                            "outsource": {
                                "shifts": 0,
                                "paid_hours": 0,
                                "fot": 0.0
                            },
                            "vacancies": {
                                "shifts": 0,
                                "paid_hours": 0,
                                "fot": 0.0
                            }
                        },
                        "combined": {
                            "shop": {
                                "shifts": 5,
                                "paid_hours": 44,
                                "fot": 0.0
                            },
                            "outsource": {
                                "shifts": 0,
                                "paid_hours": 0,
                                "fot": 0.0
                            },
                            "vacancies": {
                                "shifts": 0,
                                "paid_hours": 0,
                                "fot": 0.0
                            }
                        }
                    },
                    "work_types": {
                        "55": 4.0,
                        "56": 24.0
                    },
                    "operation_types": {
                        "685": 4.0,
                        "686": 33.0,
                        "689": 0.0
                    }
                }
            }
        }
    )
}

confirm_vacancy_response_schema_dictionary = {
    "200": openapi.Response(
        description="Vacancy confirmed",
        examples={
            "application/json":{
                "result": "Вакансия успешно принята."
            }
        }
    ),
    "400": openapi.Response(
        description="Vacancy can not be confirmed",
        examples={
            "application/json":{
                "result": "Вы не можете выйти на эту смену."
            }
        }
    ),
    "404": openapi.Response(
        description="Vacancy does not exist",
        examples={
            "application/json":{
                "result": "Такой вакансии не существует"
            }
        }
    ),
}

change_range_response_schema_dictionary = {
    "200": openapi.Response(
        description="OK",
        examples={
            "application/json":{
                "HM-001":{
                    "deleted_count": 2,
                    "existing_count": 6,
                    "created_count": 0,
                },
                "HM-002":{
                    "deleted_count": 1,
                    "existing_count": 7,
                    "created_count": 3,
                },
            }
        }
    )
}


worker_day_list_integration = {
    "200": openapi.Response(
        description='OK',
        examples={
            "application/json":[
                {
                    "id": 37165,
                    "worker_username": 111,
                    "shop_code": "200-01",
                    "type": "W",
                    "dt": "2020-07-20",
                    "dttm_work_start": "2020-07-20T05:11:30.712Z",
                    "dttm_work_end": "2020-07-20T05:22:19.712Z",
                    "comment": "string", 
                    "is_approved": True,
                    "worker_day_details": [
                    {
                        "id": 47664,
                        "work_type_id": 0,
                        "work_part": 0
                    }
                    ],
                    "is_fact": True,  
                    "work_hours": 10.5,
                    "work_hours_details": {
                        "D": 8,
                        "N": 2.5,
                    },
                    "parent_worker_day_id": 0,
                    "is_outsource": True,
                    "is_vacancy": True
                },
                {
                    "id": 37165,
                    "worker_username": 111,
                    "shop_code": "200-01",
                    "type": "H",
                    "dt": "2020-07-20",
                    "dttm_work_start": None,
                    "dttm_work_end": None,
                    "comment": "string", 
                    "is_approved": True,
                    "worker_day_details": None,
                    "is_fact": True,  
                    "work_hours": 0,
                    "parent_worker_day_id": 0,
                    "is_outsource": True,
                    "is_vacancy": False
                }
            ]
        }
    )
}

receipt_integration = {
    "200": openapi.Response(
        description='OK',
        examples={
            "application/json":{
                "shop_code": 1234,
                "dttm": "2020-07-20T11:00:00.000Z",
                "GUID": "…",
                "value": 2.3,
                "another_field": {},
            },
        }
    ),
    "201": openapi.Response(
        description='Created',
        examples={
            "application/json":{
                "shop_code": 1234,
                "dttm": "2020-07-20T11:00:00.000Z",
                "GUID": "…",
                "value": 2.3,
                "another_field": {},
            },
        }
    )
}

