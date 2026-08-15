# Collection Data

โปรแกรมเก็บข้อมูล (data collection) จากอุปกรณ์อุตสาหกรรมผ่าน **Modbus TCP** และ **OPC UA**
โดยแบ่งการเชื่อมต่อออกเป็น **Connector/Driver** แต่ละตัวมีหน้าตั้งค่าของตัวเอง ค่าที่อ่านได้จาก
Connector แบบ Client ทั้งหมดจะถูกรวมไว้ใน **Tag Store** กลางตัวเดียว ซึ่ง Connector แบบ Server
สามารถเลือกดึงค่าจาก Tag Store นั้นไปแจกจ่ายต่อให้ระบบอื่น ๆ ได้ (พร้อมใส่สูตรคำนวณ/factor)

```
[Modbus TCP Client] ─┐
[OPC UA Client]     ─┼──▶  Tag Store (กลาง)  ──┬──▶ [Modbus TCP Server]
                      │                          └──▶ [OPC UA Server]
```

## Connector ที่รองรับ

| Connector | โหมด | ตั้งค่าได้ |
|---|---|---|
| **Modbus TCP Client** | อ่านค่าจากอุปกรณ์ปลายทาง (PLC ฯลฯ) | Host/Port/Unit ID, และต่อ Register: Area, Address, **Data Type**, **Word/Byte Order (ABCD/BADC/CDAB/DCBA)**, **Factor**, Offset, **ชื่อตัวแปร (tag name)** |
| **Modbus TCP Server** | เปิดพอร์ตให้ระบบอื่นมาอ่านค่า | Listen Host/Port/Unit ID, และต่อ Register: เลือกค่าจาก Tag Store ผ่าน **Factor Expression** (เช่น `tank1_level * 1.0`) พร้อม Data Type/Word Order ที่จะ encode ออกไป |
| **OPC UA Client** | อ่านค่าจาก OPC UA Server ปลายทาง | Endpoint URL, Username/Password, และต่อ Node: Node ID, Factor, Offset, ชื่อตัวแปร |
| **OPC UA Server** | เปิด OPC UA Server ของตัวเอง | Endpoint URL, Server Name, Namespace URI, และต่อ Node: เลือกค่าจาก Tag Store ผ่าน **Factor Expression** |

Factor Expression รองรับตัวดำเนินการ `+ - * / ( )` และฟังก์ชัน `min/max/abs/round/sqrt/floor/ceil`
โดยอ้างอิงชื่อ tag ที่มาจาก Connector ฝั่ง Client ได้โดยตรง (มี dropdown "Insert system tag" ในหน้า UI
ให้เลือกแทนการพิมพ์เอง) — ประเมินผลด้วย safe evaluator (`app/expression.py`) ที่จำกัดเฉพาะนิพจน์ทาง
คณิตศาสตร์ ไม่สามารถเรียกโค้ดอื่นได้

## Historian (เก็บข้อมูลย้อนหลัง) + Trend

มีบริการพื้นหลัง (`app/historian.py`) คอย snapshot ค่าล่าสุดของทุก tag ใน Tag Store ลง**พื้นที่เก็บ
ข้อมูลย้อนหลัง (storage backend)** ตามรอบเวลาที่กำหนด (ค่าเริ่มต้นทุก 5 วินาที) พร้อม purge ข้อมูลที่เก่า
เกิน retention อัตโนมัติ (ค่าเริ่มต้น 30 วัน)

Storage backend **เลือกได้จากหน้า Settings** (admin เท่านั้น) โดยไม่ต้องแก้โค้ด มี 2 แบบ:

| Backend | รายละเอียด |
|---|---|
| **SQLite** (ค่าเริ่มต้น) | เก็บในไฟล์ SQLite เดียวกับที่เก็บ config ทั้งหมด ไม่ต้องตั้งค่าอะไรเพิ่ม เหมาะกับการใช้งานเล็ก ๆ/ทดสอบ |
| **TimescaleDB** | เก็บใน PostgreSQL/TimescaleDB แยกต่างหาก (ผ่าน `asyncpg`) กรอก Host/Port/Database/Username/Password/ ชื่อตาราง/SSL mode แล้วกด **Test Connection** ก่อน **Save** ได้ ถ้าเชื่อมต่อไม่สำเร็จระบบจะไม่บันทึกและ historian ยังคงทำงานกับ backend เดิมต่อไป (ไม่มีข้อมูลขาดหาย) |

ตอน start จะสร้างตาราง (`CREATE TABLE IF NOT EXISTS`) และพยายามเปิดใช้ TimescaleDB hypertable ให้อัตโนมัติ
(`CREATE EXTENSION IF NOT EXISTS timescaledb` + `create_hypertable(...)`) — ถ้า Postgres ปลายทางไม่ได้ติดตั้ง
extension `timescaledb` ไว้ ระบบจะ fallback ไปใช้เป็นตาราง Postgres ธรรมดาแทนโดยอัตโนมัติ (log warning
ไว้ให้เห็น) แอปยังทำงานได้ปกติ เพียงแต่ไม่ได้ partition ข้อมูลแบบ hypertable — ถ้าต้องการ hypertable จริง
ต้องติดตั้ง extension บนฝั่ง Postgres server เอง (`CREATE EXTENSION timescaledb;` ด้วยสิทธิ์ superuser หรือ
ใช้ TimescaleDB image สำเร็จรูป)

เปลี่ยน backend ระหว่างที่แอปกำลังรันอยู่ได้เลยจากหน้า Settings โดยไม่ต้อง restart แอป — historian service
จะปิดการเชื่อมต่อเดิมและสลับไปใช้ตัวใหม่ทันที (ข้อมูลเก่าที่อยู่ backend เดิมจะยังอยู่ที่เดิม ไม่ถูกย้ายตาม)

หน้า **Trend** ในเว็บใช้ข้อมูลนี้วาดกราฟเส้นย้อนหลัง (อ่านผ่าน backend ที่ config ไว้เสมอ ไม่ว่าจะเป็น
SQLite หรือ TimescaleDB) เลือกได้หลาย tag พร้อมกัน (สูงสุด 8 เส้น) เลือกช่วงเวลาสำเร็จรูป (15m/1h/6h/24h/7d)
มี crosshair + tooltip แสดงค่าทุก tag ที่จุดที่ชี้ และ auto-refresh ได้

## User Login & สิทธิ์การใช้งาน

ระบบมี login แบบ session cookie (bcrypt hash รหัสผ่าน) พร้อม 2 role:

| Role | เข้าถึงได้ |
|---|---|
| **admin** | ทุกหน้า รวมถึง Connectors (สร้าง/แก้ไข/ลบ connector, register, start/stop) และ Users |
| **viewer** | อ่านอย่างเดียว: Live Monitor และ Trend เท่านั้น (เรียก API ฝั่ง connector จะได้ 403) |

ครั้งแรกที่รันแอป (ยังไม่มี user ในระบบ) จะสร้าง user `admin` พร้อม**รหัสผ่านสุ่ม**ให้อัตโนมัติ และ
พิมพ์รหัสผ่านนั้นออกทาง log ตอน startup (หาในเทอร์มินัลบรรทัดที่ขึ้นต้นด้วย `Created default admin
user`) — ให้ล็อกอินแล้วรีบเปลี่ยนรหัสผ่าน (เมนู "Change password" มุมล่างซ้าย) หรือสร้าง user ใหม่จากหน้า
**Users** (admin เท่านั้น)

## เริ่มใช้งาน

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

uvicorn app.main:app --host 0.0.0.0 --port 8000
```

เปิดเบราว์เซอร์ไปที่ `http://localhost:8000` จะเจอหน้า login ก่อน (ดูรหัสผ่าน admin เริ่มต้นจาก log
ตามด้านบน) จากนั้นจะเจอหน้า **Connectors** สำหรับสร้าง/ตั้งค่า connector, **Live Monitor** สำหรับดูค่า
ล่าสุดแบบเรียลไทม์, **Trend** สำหรับดูกราฟย้อนหลัง, **Users** สำหรับจัดการผู้ใช้ และ **Settings** สำหรับ
เลือก/ตั้งค่า storage backend ของ historian (SQLite หรือ TimescaleDB) — ทั้งหมด admin เท่านั้นยกเว้น Live
Monitor กับ Trend

ฐานข้อมูล (การตั้งค่าทั้งหมด) เก็บเป็นไฟล์ SQLite ที่ `data/collection_data.db` โดยอัตโนมัติ
(เปลี่ยน path ได้ด้วย env var `COLLECTION_DATA_DB`) ส่วนค่าที่อ่านได้แบบเรียลไทม์เก็บใน memory เท่านั้น

Connector ที่ตั้ง `enabled = true` จะถูกสั่ง start ให้อัตโนมัติทุกครั้งที่แอปเริ่มทำงาน และการแก้ไข
config/register ใด ๆ ระหว่างที่ connector กำลัง running อยู่ จะ restart ให้อัตโนมัติเพื่อให้ค่าที่แก้ไข
มีผลทันที

## โครงสร้างโปรเจกต์

```
app/
  main.py                FastAPI app + lifespan (start/stop driver, historian, bootstrap admin)
  models.py               SQLAlchemy ORM (Connector, config, register/node, TagHistory, User, Session)
  schemas.py               Pydantic request/response schemas
  database.py               SQLite engine/session
  tag_store.py               Tag Store กลางแบบ async-safe
  expression.py               Safe expression evaluator สำหรับ factor expression
  historian.py                 HistorianService: snapshot loop + purge, สลับ backend runtime ได้
  historian_backends.py         HistorianBackend interface: Sqlite / TimescaleDb (asyncpg)
  auth.py                        bcrypt hashing, session cookie, get_current_user/require_admin
  drivers/
    codec.py                  แปลงค่า <-> Modbus register (data type + word order)
    base.py                    Base class ของทุก driver
    modbus_client.py            Modbus TCP Client driver (poll -> tag store)
    modbus_server.py             Modbus TCP Server driver (pull-based datastore จาก tag store)
    opcua_client.py               OPC UA Client driver
    opcua_server.py                OPC UA Server driver (push ค่าเข้า node ตาม publish interval)
    manager.py                     DriverManager: start/stop/restart driver ตาม config ใน DB
  api/
    connectors.py                   REST API: CRUD connector + config + register/node (admin only)
    values.py                        REST API: ค่า live, ประวัติ (history), รายชื่อ tag (ต้อง login)
    auth_routes.py                    login/logout/me/change-password
    users.py                          REST API: จัดการ user (admin only)
    settings.py                        REST API: historian storage settings + test-connection (admin only)
frontend/
  index.html, css/style.css
  js/api.js, app.js               shared fetch wrapper, router, Connectors + Live Monitor
  js/trend.js                      Trend page (SVG line chart)
  js/users.js                      Users management page
  js/settings.js                    Settings page (historian storage backend)
  js/auth.js                       login screen, session bootstrap, role-aware nav
tests/                               pytest: unit test ของ codec/expression/historian + auth/history/
                                      settings API tests + integration test เปิด Modbus server+client
                                      จริงผ่าน TCP loopback + TimescaleDB backend test ผ่าน Postgres จริง
                                      (skip อัตโนมัติถ้าไม่มี Postgres ให้ต่อ)
```

## รันเทส

```bash
pip install -r requirements-dev.txt
pytest -q
```

ชุดเทสมี unit test ครบทุก data type/word order ของ `codec.py`, ทุก edge case ของ `expression.py`,
และ integration test ที่รัน `ModbusTcpServerDriver` กับ `ModbusTcpClientDriver` จริงผ่าน TCP loopback
เพื่อยืนยันว่าทั้ง pipeline (encode → เครือข่าย → decode → factor → tag store → expression) ทำงานถูกต้อง

## หมายเหตุ

- **การเขียนค่ากลับ (write-back):** ฝั่ง Modbus TCP Server รองรับการเขียนจาก master ภายนอกเฉพาะ
  register ที่ expression เป็นชื่อ tag เปล่า ๆ (ไม่มีสูตรคำนวณ) เท่านั้น ซึ่งจะเขียนค่ากลับเข้า Tag Store
  ให้โดยตรง — ใช้สำหรับกรณี setpoint/เขียนควบคุมง่าย ๆ ส่วน register ที่เป็นสูตรคำนวณจะไม่รับการเขียน
- ชื่อ tag (variable name) ของ Modbus Client register และ OPC UA Client node ต้องไม่ซ้ำกันทั้งระบบ
  เพราะทุก tag แชร์ namespace เดียวกันใน Tag Store
- Session cookie เป็น httponly + SameSite=Lax อายุ 7 วัน เก็บใน SQLite (`user_sessions`) ไม่ใช่ JWT
  จึง revoke ได้ทันทีด้วยการลบ session/logout ระบบไม่มี CORS เปิดไว้ (ค่า default ของ FastAPI) จึงไม่ต้อง
  ทำ CSRF token เพิ่มสำหรับการใช้งานทั่วไปในเครือข่ายปิด (OT network)
- รหัสผ่านของ TimescaleDB เก็บเป็น plaintext ในตาราง `historian_settings` (เหมือนกับรหัสผ่านของ OPC UA
  client ที่มีอยู่แล้วในระบบ) — ไม่ได้เข้ารหัสเพิ่ม ควรจำกัดสิทธิ์การเข้าถึงไฟล์ฐานข้อมูล/เครื่องเซิร์ฟเวอร์
  ให้เหมาะสม
- ชื่อตาราง TimescaleDB (`ts_table`) ถูก validate ทั้งฝั่ง API (`^[A-Za-z_][A-Za-z0-9_]{0,62}$`) และฝั่ง
  backend เอง ก่อนนำไปต่อ string เป็น SQL DDL/DML เพื่อป้องกัน SQL injection ผ่านชื่อตาราง
- ทดสอบ backend ของ TimescaleDB จริงได้ด้วยการรัน PostgreSQL ในเครื่อง (`pg_ctlcluster <ver> main start`
  หรือ `docker run -e POSTGRES_PASSWORD=postgres -p 5432:5432 postgres`) แล้วตั้ง env var `TEST_PG_HOST`,
  `TEST_PG_PORT`, `TEST_PG_USER`, `TEST_PG_PASSWORD`, `TEST_PG_DATABASE` ก่อนรัน `pytest` (ถ้าไม่มี Postgres
  ให้ต่อ เทสกลุ่มนี้จะ skip อัตโนมัติ ไม่ fail)
