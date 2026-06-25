-- oracle/package.sql
--
-- Logistics Event Processing
-- GPS event processing package.
--
-- The Python application calls this package after validating and transforming
-- an incoming GPS event. The package resolves driver_code and vehicle_code
-- to internal Oracle primary keys, then inserts the normalised GPS row.
SET SERVEROUTPUT ON;
PROMPT Creating event_processing_pkg...
--------------------------------------------------------------------------------
-- Package specification
--------------------------------------------------------------------------------
CREATE OR REPLACE PACKAGE event_processing_pkg AS
  PROCEDURE insert_gps_crumb (
    p_source_system          IN VARCHAR2,
    p_external_event_id      IN VARCHAR2,
    p_event_timestamp        IN TIMESTAMP,
    p_driver_code            IN VARCHAR2,
    p_vehicle_code           IN VARCHAR2,
    p_latitude               IN NUMBER,
    p_longitude              IN NUMBER,
    p_speed_kmh              IN NUMBER,
    p_heading_degrees        IN NUMBER,
    p_gps_accuracy_m         IN NUMBER,
    p_battery_level_percent  IN NUMBER
  );
END event_processing_pkg;
/
SHOW ERRORS PACKAGE event_processing_pkg;
--------------------------------------------------------------------------------
-- Package body
--------------------------------------------------------------------------------
CREATE OR REPLACE PACKAGE BODY event_processing_pkg AS
  PROCEDURE insert_gps_crumb (
    p_source_system          IN VARCHAR2,
    p_external_event_id      IN VARCHAR2,
    p_event_timestamp        IN TIMESTAMP,
    p_driver_code            IN VARCHAR2,
    p_vehicle_code           IN VARCHAR2,
    p_latitude               IN NUMBER,
    p_longitude              IN NUMBER,
    p_speed_kmh              IN NUMBER,
    p_heading_degrees        IN NUMBER,
    p_gps_accuracy_m         IN NUMBER,
    p_battery_level_percent  IN NUMBER
  ) AS
    v_driver_id   drivers.driver_id%TYPE;
    v_vehicle_id  vehicles.vehicle_id%TYPE;
  BEGIN
    --------------------------------------------------------------------------
    -- Resolve active driver
    --------------------------------------------------------------------------
    BEGIN
      SELECT driver_id
      INTO v_driver_id
      FROM drivers
      WHERE driver_code = p_driver_code
        AND active_flag = 'Y';
    EXCEPTION
      WHEN NO_DATA_FOUND THEN
        RAISE_APPLICATION_ERROR(
          -20001,
          'Active driver not found for driver_code: ' || p_driver_code
        );
      WHEN TOO_MANY_ROWS THEN
        RAISE_APPLICATION_ERROR(
          -20002,
          'Multiple active drivers found for driver_code: ' || p_driver_code
        );
    END;
    --------------------------------------------------------------------------
    -- Resolve active vehicle
    --------------------------------------------------------------------------
    BEGIN
      SELECT vehicle_id
      INTO v_vehicle_id
      FROM vehicles
      WHERE vehicle_code = p_vehicle_code
        AND active_flag = 'Y';
    EXCEPTION
      WHEN NO_DATA_FOUND THEN
        RAISE_APPLICATION_ERROR(
          -20003,
          'Active vehicle not found for vehicle_code: ' || p_vehicle_code
        );
      WHEN TOO_MANY_ROWS THEN
        RAISE_APPLICATION_ERROR(
          -20004,
          'Multiple active vehicles found for vehicle_code: ' || p_vehicle_code
        );
    END;
    --------------------------------------------------------------------------
    -- Insert normalised GPS row
    --------------------------------------------------------------------------
    INSERT INTO gps (
      source_system,
      external_event_id,
      event_timestamp,
      driver_id,
      vehicle_id,
      latitude,
      longitude,
      speed_kmh,
      heading_degrees,
      gps_accuracy_m,
      battery_level_percent
    )
    VALUES (
      p_source_system,
      p_external_event_id,
      p_event_timestamp,
      v_driver_id,
      v_vehicle_id,
      p_latitude,
      p_longitude,
      p_speed_kmh,
      p_heading_degrees,
      p_gps_accuracy_m,
      p_battery_level_percent
    );
  EXCEPTION
    WHEN DUP_VAL_ON_INDEX THEN
      RAISE_APPLICATION_ERROR(
        -20005,
        'Duplicate GPS event for source_system/external_event_id: '
        || p_source_system || '/' || p_external_event_id
      );
    WHEN OTHERS THEN
      RAISE;
  END insert_gps_crumb;
END event_processing_pkg;
/
SHOW ERRORS PACKAGE BODY event_processing_pkg;
--------------------------------------------------------------------------------
-- Completion message
--------------------------------------------------------------------------------
BEGIN
  DBMS_OUTPUT.PUT_LINE('Package created successfully.');
  DBMS_OUTPUT.PUT_LINE('Package: event_processing_pkg');
  DBMS_OUTPUT.PUT_LINE('Procedure: insert_gps_crumb');
END;
/