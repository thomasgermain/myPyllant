import pytest
from pydantic import ValidationError

from myPyllant.api import MyPyllantAPI
from .generate_test_data import DATA_DIR

from ..models import (
    Home,
    System,
    ZoneHeating,
    ZoneTimeProgram,
    Device,
    AmbisenseRoom,
    RoomTimeProgram,
    AmbisenseDevice,
)
from ..enums import ZoneHeatingOperatingMode, ControlIdentifier
from .utils import list_test_data, load_test_data


@pytest.mark.parametrize("test_data", list_test_data())
async def test_systems(
    mypyllant_aioresponses, mocked_api: MyPyllantAPI, test_data
) -> None:
    with mypyllant_aioresponses(test_data) as _:
        system = await anext(mocked_api.get_systems())

        assert isinstance(system, System), "Expected System return type"
        assert isinstance(system.home, Home)
        assert isinstance(system.home.system_id, str)
        await mocked_api.aiohttp_session.close()


async def test_type_validation() -> None:
    with pytest.raises(ValidationError):
        ZoneHeating.from_api(
            control_identifier=ControlIdentifier.TLI,
            manual_mode_setpoint_heating="shouldbenumber",
            operation_mode_heating=ZoneHeatingOperatingMode.MANUAL,
            time_program_heating={},
            set_back_temperature=15.0,
        )
    with pytest.raises(ValueError):
        ZoneHeating.from_api(
            control_identifier=ControlIdentifier.TLI,
            manual_mode_setpoint_heating=15.0,
            operation_mode_heating="INVALID",
            time_program_heating={},
            set_back_temperature=15.0,
        )


@pytest.mark.parametrize("test_data", list_test_data())
async def test_trouble_codes(
    mypyllant_aioresponses, mocked_api: MyPyllantAPI, test_data
) -> None:
    with mypyllant_aioresponses(test_data) as _:
        system = await anext(
            mocked_api.get_systems(include_diagnostic_trouble_codes=True)
        )
        assert isinstance(system.diagnostic_trouble_codes, list)
        if not system.diagnostic_trouble_codes:
            await mocked_api.aiohttp_session.close()
            pytest.skip("No diagnostic trouble codes in test data, skipping")
        dtc = system.diagnostic_trouble_codes[0]
        assert isinstance(dtc, dict)
        assert isinstance(dtc["codes"], list)

        system.diagnostic_trouble_codes[0]["codes"] = [1, 2]
        assert system.has_diagnostic_trouble_codes

        system.diagnostic_trouble_codes = [{"codes": []}]
        assert not system.has_diagnostic_trouble_codes
        await mocked_api.aiohttp_session.close()


async def test_ventilation(mypyllant_aioresponses, mocked_api: MyPyllantAPI) -> None:
    test_data = load_test_data(DATA_DIR / "ventilation")
    with mypyllant_aioresponses(test_data) as _:
        system = await anext(mocked_api.get_systems())
        assert isinstance(system.ventilation, list)
        devices = [d for d in system.devices if d.type == "ventilation"]
        assert devices[0].device_type == "VENTILATION"
        await mocked_api.aiohttp_session.close()


async def test_time_program_overlap() -> None:
    # Should not raise an exception
    time_program = ZoneTimeProgram.from_api(
        **{
            "monday": [
                {"start_time": 360, "end_time": 1320, "setpoint": 21.0},
                {"start_time": 1320, "end_time": 1340, "setpoint": 22.0},
            ]
        }
    )
    time_program.check_overlap()

    time_program = ZoneTimeProgram.from_api(
        **{
            "monday": [
                {"start_time": 360, "end_time": 1320, "setpoint": 21.0},
                {"start_time": 380, "end_time": 420, "setpoint": 22.0},
            ]
        }
    )
    with pytest.raises(ValueError):
        time_program.check_overlap()


async def test_rts_statistics(mypyllant_aioresponses, mocked_api: MyPyllantAPI) -> None:
    data_list = [
        load_test_data(DATA_DIR / "vrc700_mpc_rts.yaml"),
        load_test_data(DATA_DIR / "rts"),
    ]
    for test_data in data_list:
        with mypyllant_aioresponses(test_data) as _:
            system = await anext(mocked_api.get_systems(include_rts=True))
            assert isinstance(system.rts, dict)
            assert len(system.rts.get("statistics", [])) > 0
            rts_device_id = system.rts["statistics"][0]["device_id"]
            d: Device = [d for d in system.devices if d.device_uuid == rts_device_id][0]
            assert isinstance(d.on_off_cycles, int)
            assert isinstance(d.operation_time, int)
    await mocked_api.aiohttp_session.close()


async def test_mpc(mypyllant_aioresponses, mocked_api: MyPyllantAPI) -> None:
    test_data = load_test_data(DATA_DIR / "vrc700_mpc_rts.yaml")
    with mypyllant_aioresponses(test_data) as _:
        system = await anext(mocked_api.get_systems(include_mpc=True))
        assert isinstance(system.mpc, dict)
        assert len(system.mpc.get("devices", [])) > 0
        mpc_device_id = system.mpc["devices"][0]["device_id"]
        d: Device = [d for d in system.devices if d.device_uuid == mpc_device_id][0]
        assert isinstance(d.current_power, int)
    await mocked_api.aiohttp_session.close()


async def test_extra_system_state_properties(
    mypyllant_aioresponses, mocked_api: MyPyllantAPI
) -> None:
    test_data = load_test_data(DATA_DIR / "two_systems")
    with mypyllant_aioresponses(test_data) as _:
        system = await anext(mocked_api.get_systems())
        assert system.cylinder_temperature_sensor_top_ch is not None
        assert system.cylinder_temperature_sensor_top_dhw is not None
        assert system.cylinder_temperature_sensor_bottom_dhw is not None
    await mocked_api.aiohttp_session.close()


async def test_ambisense(mypyllant_aioresponses, mocked_api: MyPyllantAPI) -> None:
    test_data = load_test_data(DATA_DIR / "ambisense")
    with mypyllant_aioresponses(test_data) as _:
        system = await anext(mocked_api.get_systems(include_ambisense_rooms=True))
        assert len(system.ambisense_rooms) > 0
        assert isinstance(system.ambisense_rooms[0], AmbisenseRoom)
        for room in system.ambisense_rooms:
            assert isinstance(room.name, str)
            assert isinstance(room.room_configuration.devices[0], AmbisenseDevice)
            assert len(room.room_configuration.devices[0].name) > 0
            assert isinstance(room.time_program, RoomTimeProgram)
            assert isinstance(room.room_configuration.current_temperature, float)
            if room.room_index == 1:
                assert isinstance(room.time_program.monday[0].start_time, int)
                assert isinstance(
                    room.time_program.monday[0].temperature_setpoint, float
                )
    await mocked_api.aiohttp_session.close()
