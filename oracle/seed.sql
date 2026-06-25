-- oracle/seed.sql
--
-- Logistics Event Processing
-- GPS reference data.
--
-- This script inserts the driver and vehicle records required by the GPS
-- processing application. Incoming GPS events use driver_code and vehicle_code.
-- The PL/SQL package resolves those codes to the internal driver_id and
-- vehicle_id primary keys before inserting into gps.
SET SERVEROUTPUT ON;
PROMPT Seeding logistics GPS reference data...
--------------------------------------------------------------------------------
-- Clear existing reference data
--------------------------------------------------------------------------------
-- gps is cleared first because it references drivers and vehicles.
DELETE FROM gps;
DELETE FROM vehicles;
DELETE FROM drivers;
--------------------------------------------------------------------------------
-- Seed drivers
--------------------------------------------------------------------------------
INSERT INTO drivers (
  driver_code,
  driver_name,
  active_flag
)
VALUES (
  'DRV1027',
  'Alex Morgan',
  'Y'
);
INSERT INTO drivers (
  driver_code,
  driver_name,
  active_flag
)
VALUES (
  'DRV2044',
  'Priya Shah',
  'Y'
);
INSERT INTO drivers (
  driver_code,
  driver_name,
  active_flag
)
VALUES (
  'DRV3098',
  'Michael Tan',
  'Y'
);
INSERT INTO drivers (
  driver_code,
  driver_name,
  active_flag
)
VALUES (
  'DRV4112',
  'Sarah Williams',
  'N'
);
--------------------------------------------------------------------------------
-- Seed vehicles
--------------------------------------------------------------------------------
INSERT INTO vehicles (
  vehicle_code,
  registration_number,
  active_flag
)
VALUES (
  'VH-4412',
  'BAC-4412',
  'Y'
);
INSERT INTO vehicles (
  vehicle_code,
  registration_number,
  active_flag
)
VALUES (
  'VH-8821',
  'BAC-8821',
  'Y'
);
INSERT INTO vehicles (
  vehicle_code,
  registration_number,
  active_flag
)
VALUES (
  'VH-1934',
  'BAC-1934',
  'Y'
);
INSERT INTO vehicles (
  vehicle_code,
  registration_number,
  active_flag
)
VALUES (
  'VH-7705',
  'BAC-7705',
  'N'
);
COMMIT;
--------------------------------------------------------------------------------
-- Completion message
--------------------------------------------------------------------------------
BEGIN
  DBMS_OUTPUT.PUT_LINE('Seed data inserted successfully.');
  DBMS_OUTPUT.PUT_LINE('Drivers inserted: 4');
  DBMS_OUTPUT.PUT_LINE('Vehicles inserted: 4');
END;
/