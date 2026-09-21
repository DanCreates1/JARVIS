ALTER TABLE remote_enrollments
ADD COLUMN enrollment_protocol_version TEXT NOT NULL DEFAULT '1'
    CHECK (enrollment_protocol_version IN ('1', '2'));

ALTER TABLE remote_enrollments
ADD COLUMN server_origin TEXT;

ALTER TABLE remote_devices
ADD COLUMN enrollment_protocol_version TEXT NOT NULL DEFAULT '1'
    CHECK (enrollment_protocol_version IN ('1', '2'));

ALTER TABLE remote_devices
ADD COLUMN server_origin TEXT;
