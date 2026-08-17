from __future__ import annotations

from tests.conftest import set_admin_password


def _login_admin(client):
    set_admin_password("test-password-123")
    r = client.post("/api/auth/login", json={"username": "admin", "password": "test-password-123"})
    assert r.status_code == 200


def _create_connector(client, name, type_):
    r = client.post("/api/connectors", json={"name": name, "type": type_, "enabled": False})
    assert r.status_code == 201
    return r.json()["id"]


def _upload(client, url, csv_text):
    return client.post(url, files={"file": ("registers.csv", csv_text, "text/csv")})


def test_modbus_client_register_export_csv(client):
    _login_admin(client)
    cid = _create_connector(client, "PLC1", "modbus_tcp_client")
    client.post(f"/api/connectors/{cid}/modbus-client-registers", json={
        "tag_name": "temp1", "area": "holding_register", "address": 100,
        "data_type": "float32", "word_order": "CDAB", "factor": 0.1, "offset": 0.0,
    })

    r = client.get(f"/api/connectors/{cid}/modbus-client-registers/export")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"]
    lines = r.text.strip().splitlines()
    assert lines[0].split(",")[:5] == ["tag_name", "area", "address", "data_type", "word_order"]
    assert "temp1" in lines[1]
    assert "CDAB" in lines[1]


def test_modbus_client_register_import_creates_and_updates(client):
    _login_admin(client)
    cid = _create_connector(client, "PLC1", "modbus_tcp_client")
    client.post(f"/api/connectors/{cid}/modbus-client-registers", json={
        "tag_name": "temp1", "area": "holding_register", "address": 100, "data_type": "uint16",
    })

    csv_text = (
        "tag_name,area,address,data_type,word_order,factor,offset,enabled,description\n"
        "temp1,holding_register,200,float32,ABCD,2.0,1.0,true,updated via csv\n"
        "temp2,input_register,10,int16,ABCD,1.0,0.0,true,brand new\n"
    )
    r = _upload(client, f"/api/connectors/{cid}/modbus-client-registers/import", csv_text)
    assert r.status_code == 200
    body = r.json()
    assert body["created"] == 1
    assert body["updated"] == 1
    assert body["errors"] == []

    regs = {r["tag_name"]: r for r in client.get(f"/api/connectors/{cid}/modbus-client-registers").json()}
    assert regs["temp1"]["address"] == 200
    assert regs["temp1"]["data_type"] == "float32"
    assert regs["temp1"]["factor"] == 2.0
    assert regs["temp2"]["area"] == "input_register"


def test_modbus_client_register_import_reports_row_errors(client):
    _login_admin(client)
    cid = _create_connector(client, "PLC1", "modbus_tcp_client")

    csv_text = (
        "tag_name,area,address,data_type,word_order,factor,offset,enabled,description\n"
        "good_tag,holding_register,1,uint16,ABCD,1,0,true,\n"
        ",holding_register,2,uint16,ABCD,1,0,true,missing tag name\n"
        "bad_address,holding_register,not_a_number,uint16,ABCD,1,0,true,\n"
        "bad_area,not_a_real_area,3,uint16,ABCD,1,0,true,\n"
    )
    r = _upload(client, f"/api/connectors/{cid}/modbus-client-registers/import", csv_text)
    assert r.status_code == 200
    body = r.json()
    assert body["created"] == 1
    assert len(body["errors"]) == 3
    assert any("row 3" in e for e in body["errors"])
    assert any("row 4" in e for e in body["errors"])
    assert any("row 5" in e for e in body["errors"])


def test_modbus_client_register_import_rejects_cross_type_tag_collision(client):
    _login_admin(client)
    opcua_id = _create_connector(client, "OpcClient", "opcua_client")
    client.post(f"/api/connectors/{opcua_id}/opcua-client-nodes", json={"tag_name": "shared_tag", "node_id": "ns=2;s=X"})

    modbus_id = _create_connector(client, "PLC1", "modbus_tcp_client")
    csv_text = "tag_name,area,address,data_type\nshared_tag,holding_register,1,uint16\n"
    r = _upload(client, f"/api/connectors/{modbus_id}/modbus-client-registers/import", csv_text)
    body = r.json()
    assert body["created"] == 0
    assert any("already used" in e for e in body["errors"])


def test_modbus_server_register_import_upserts_by_area_and_address(client):
    _login_admin(client)
    cid = _create_connector(client, "GatewayServer", "modbus_tcp_server")
    client.post(f"/api/connectors/{cid}/modbus-server-registers", json={
        "name": "out1", "area": "holding_register", "address": 50, "expression": "1 + 1",
    })

    csv_text = (
        "name,area,address,data_type,word_order,expression,enabled\n"
        "out1_renamed,holding_register,50,uint16,ABCD,5 + 5,true\n"
        "out2,holding_register,60,uint16,ABCD,tank1_level,true\n"
    )
    r = _upload(client, f"/api/connectors/{cid}/modbus-server-registers/import", csv_text)
    body = r.json()
    assert body["created"] == 1
    assert body["updated"] == 1
    assert body["errors"] == []

    regs = client.get(f"/api/connectors/{cid}/modbus-server-registers").json()
    by_addr = {r["address"]: r for r in regs}
    assert by_addr[50]["name"] == "out1_renamed"
    assert by_addr[50]["expression"] == "5 + 5"
    assert by_addr[60]["expression"] == "tank1_level"


def test_modbus_server_register_import_reports_invalid_expression(client):
    _login_admin(client)
    cid = _create_connector(client, "GatewayServer", "modbus_tcp_server")
    csv_text = "name,area,address,expression\nbad,holding_register,1,this is not valid python-ish syntax +\n"
    r = _upload(client, f"/api/connectors/{cid}/modbus-server-registers/import", csv_text)
    body = r.json()
    assert body["created"] == 0
    assert any("invalid expression" in e for e in body["errors"])


def test_opcua_client_node_export_and_import(client):
    _login_admin(client)
    cid = _create_connector(client, "OpcClient", "opcua_client")
    client.post(f"/api/connectors/{cid}/opcua-client-nodes", json={"tag_name": "level1", "node_id": "ns=2;s=Old"})

    r = client.get(f"/api/connectors/{cid}/opcua-client-nodes/export")
    assert r.status_code == 200
    assert "level1" in r.text

    csv_text = "tag_name,node_id,factor,offset,enabled,description\nlevel1,ns=2;s=New,2.0,0,true,\nlevel2,ns=2;s=Another,1,0,true,\n"
    r = _upload(client, f"/api/connectors/{cid}/opcua-client-nodes/import", csv_text)
    body = r.json()
    assert body["created"] == 1
    assert body["updated"] == 1

    nodes = {n["tag_name"]: n for n in client.get(f"/api/connectors/{cid}/opcua-client-nodes").json()}
    assert nodes["level1"]["node_id"] == "ns=2;s=New"
    assert nodes["level2"]["node_id"] == "ns=2;s=Another"


def test_opcua_server_node_export_and_import(client):
    _login_admin(client)
    cid = _create_connector(client, "OpcServer", "opcua_server")
    client.post(f"/api/connectors/{cid}/opcua-server-nodes", json={"node_name": "Node1", "expression": "1"})

    r = client.get(f"/api/connectors/{cid}/opcua-server-nodes/export")
    assert r.status_code == 200
    assert "Node1" in r.text

    csv_text = "node_name,expression,enabled\nNode1,42,true\nNode2,7 * 6,true\n"
    r = _upload(client, f"/api/connectors/{cid}/opcua-server-nodes/import", csv_text)
    body = r.json()
    assert body["created"] == 1
    assert body["updated"] == 1

    nodes = {n["node_name"]: n for n in client.get(f"/api/connectors/{cid}/opcua-server-nodes").json()}
    assert nodes["Node1"]["expression"] == "42"
    assert nodes["Node2"]["expression"] == "7 * 6"


def test_restart_false_skips_driver_restart_but_still_saves(client):
    _login_admin(client)
    cid = _create_connector(client, "PLC1", "modbus_tcp_client")
    r = client.post(f"/api/connectors/{cid}/modbus-client-registers?restart=false", json={
        "tag_name": "temp1", "area": "holding_register", "address": 1, "data_type": "uint16",
    })
    assert r.status_code == 201
    regs = client.get(f"/api/connectors/{cid}/modbus-client-registers").json()
    assert len(regs) == 1
