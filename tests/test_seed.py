from app.storage.memory import InMemoryStore
from app.storage.seed import seed_store


def test_seed_creates_two_doctors_and_many_patients():
    store = InMemoryStore()
    seed_store(store)
    u1 = store.users.get("user-001")
    u2 = store.users.get("user-002")
    assert u1 is not None and u1.employee_id == "12345"
    assert u2 is not None and u2.employee_id == "12346"
    assert u1.password == "password"  # 모킹

    p_lee = store.patients.list_by_employee("12345")
    p_kim = store.patients.list_by_employee("12346")
    assert len(p_lee) + len(p_kim) == 150
    assert len(p_lee) > 0
    assert len(p_kim) > 0


def test_seed_patient_types_have_all_three():
    store = InMemoryStore()
    seed_store(store)
    types = {p.patient_type for p in store.patients.list_by_employee("12345")} | \
            {p.patient_type for p in store.patients.list_by_employee("12346")}
    assert {"inpatient", "outpatient", "emergency"} <= {t.value for t in types}
