import pytest

from cloud_server import app as app_module

ALL_FIELDS = ["id", "device_id", "ts", "temperature", "humidity"]
NUMERIC_FIELDS = ["id", "ts", "temperature", "humidity"]
FLOAT_FIELDS = ["temperature", "humidity"]


def get_valid_reading():
    return {"id": 1, "device_id": "dev-1", "ts": 1000, "temperature": 21.5, "humidity": 40.0}


@pytest.fixture
def client():
    return app_module.app.test_client()


class TestParseReading:
    def test_valid_reading(self):
        reading = get_valid_reading()

        row = app_module.parse_reading(reading, received_at=123)

        assert row == {
            "edge_id": 1,
            "device_id": "dev-1",
            "ts": 1000,
            "temperature": 21.5,
            "humidity": 40.0,
            "received_at": 123,
        }

    def test_numeric_strings_are_converted(self):
        reading = get_valid_reading()
        reading["id"] = "5"
        reading["ts"] = "10"
        reading["temperature"] = "1.5"
        reading["humidity"] = "2"

        row = app_module.parse_reading(reading, received_at=0)

        assert row["edge_id"] == 5
        assert row["ts"] == 10
        assert row["temperature"] == 1.5
        assert row["humidity"] == 2.0
        assert isinstance(row["humidity"], float)

    @pytest.mark.parametrize("field", ALL_FIELDS)
    def test_missing_field_raises_key_error(self, field):
        reading = get_valid_reading()
        del reading[field]

        with pytest.raises(KeyError):
            app_module.parse_reading(reading, received_at=0)

    @pytest.mark.parametrize("field", NUMERIC_FIELDS)
    def test_non_numeric_string_raises_value_error(self, field):
        reading = get_valid_reading()
        reading[field] = "abc"

        with pytest.raises(ValueError):
            app_module.parse_reading(reading, received_at=0)

    @pytest.mark.parametrize("field", NUMERIC_FIELDS)
    def test_null_raises_type_error(self, field):
        reading = get_valid_reading()
        reading[field] = None

        with pytest.raises(TypeError):
            app_module.parse_reading(reading, received_at=0)

    @pytest.mark.parametrize("field", FLOAT_FIELDS)
    @pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf"), "nan"])
    def test_non_finite_numbers_are_rejected(self, field, value):
        reading = get_valid_reading()
        reading[field] = value

        with pytest.raises(ValueError):
            app_module.parse_reading(reading, received_at=0)


class TestIngest:
    def test_invalid_json_returns_400(self, client):
        response = client.post("/api/ingest", data="not json", content_type="application/json")

        assert response.status_code == 400
        assert response.get_json() == {"error": "bad payload"}

    @pytest.mark.parametrize("payload", [[], [1, 2], "text", 42])
    def test_payload_must_be_an_object(self, client, payload):
        response = client.post("/api/ingest", json=payload)

        assert response.status_code == 400

    @pytest.mark.parametrize("readings", ["abc", {"a": 1}, 5, None])
    def test_readings_must_be_a_list(self, client, readings):
        response = client.post("/api/ingest", json={"readings": readings})

        assert response.status_code == 400
