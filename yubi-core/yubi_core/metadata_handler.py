#!/usr/bin/env python3
import json
from jsonschema import Draft7Validator, RefResolver, exceptions
import uuid as uuid_mod
from typing import Tuple

import rclpy
from rclpy.node import Node

from std_msgs.msg import String
from std_srvs.srv import Trigger
from airoa_data_msgs.srv import StringTrigger

from airoa_metadata.schemas import load_schema
from airoa_metadata.versions.v2_0 import (
    MetadataV2_0,
    FileV2_0,
    RobotV2_0,
    EnvironmentV2_0,
    RunnerV2_0,
    DeviceV2_0,
    ProgramV2_0,
    SourceV2_0,
    EpisodeV2_0,
    SegmentV2_0,
)


class MetadataV2Handler(Node):
    def __init__(self):
        super().__init__("metadata_handler")

        # Publishers
        self.metadata_json_pub = self.create_publisher(String, "~/metadata_json", 10)

        # Service servers
        self.create_service(Trigger, "~/initialize_metadata", self.initialize_metadata_callback)
        self.create_service(StringTrigger, "~/set_episode_uuid", self.set_episode_uuid_callback)
        self.create_service(StringTrigger, "~/add_file", self.add_file_callback)
        self.create_service(StringTrigger, "~/set_robot", self.set_robot_callback)
        self.create_service(StringTrigger, "~/set_environment", self.set_environment_callback)
        self.create_service(StringTrigger, "~/set_runner", self.set_runner_callback)
        self.create_service(StringTrigger, "~/set_devices", self.set_devices_callback)
        self.create_service(StringTrigger, "~/add_program", self.add_program_callback)
        self.create_service(StringTrigger, "~/extend_programs", self.extend_programs_callback)
        self.create_service(StringTrigger, "~/add_label", self.add_label_callback)
        self.create_service(StringTrigger, "~/set_episode", self.set_episode_callback)
        self.create_service(StringTrigger, "~/set_task", self.set_task_callback)
        self.create_service(StringTrigger, "~/add_segment", self.add_segment_callback)
        self.create_service(Trigger, "~/remove_last_segment", self.remove_last_segment_callback)
        self.create_service(StringTrigger, "~/override_last_segment_success", self.override_last_segment_success)
        self.create_service(Trigger, "~/get_verified_metadata", self.get_verified_metadata_callback)

        # Operator-selected task for the current episode. Serialized as a top-level
        # ``task`` object in meta.json (the V2.0 schema permits extra top-level keys),
        # so the uploader can stamp ``task=<id>`` into the canonical object key and the
        # ingest side can route by task without opening the bag. ``id`` is a routing
        # slug; ``instruction`` is the free-text language string. ``None`` until a task
        # is set (via ``~/set_task``) → meta.json carries no ``task`` and the uploader
        # falls back to ``unassigned``. Set/cleared by ``__initialize_metadata``.
        self.metadata = self.__initialize_metadata()

        # set up JSON schema validators
        self.__setup_validators()

        self.create_timer(1.0, self.process_step)

    def __setup_validators(self):
        self.schema = load_schema("2.0")
        self.schema_validator = Draft7Validator(self.schema)

        self.file_schema = self.schema["$defs"]["File"]
        self.file_validator = Draft7Validator(self.file_schema, resolver=RefResolver.from_schema(self.schema))

        self.robot_schema = self.schema["$defs"]["Robot"]
        self.robot_validator = Draft7Validator(self.robot_schema, resolver=RefResolver.from_schema(self.schema))

        self.environment_schema = self.schema["$defs"]["Environment"]
        self.environment_validator = Draft7Validator(self.environment_schema, resolver=RefResolver.from_schema(self.schema))

        self.runner_schema = self.schema["$defs"]["Runner"]
        self.runner_validator = Draft7Validator(self.runner_schema, resolver=RefResolver.from_schema(self.schema))

        self.device_schema = self.schema["$defs"]["Device"]
        self.device_validator = Draft7Validator(self.device_schema, resolver=RefResolver.from_schema(self.schema))

        self.program_schema = self.schema["$defs"]["Program"]
        self.program_validator = Draft7Validator(self.program_schema, resolver=RefResolver.from_schema(self.schema))

        self.programs_schema = self.schema["properties"]["programs"]
        self.programs_validator = Draft7Validator(self.programs_schema, resolver=RefResolver.from_schema(self.schema))

        self.episode_schema = self.schema["$defs"]["Episode"]
        self.episode_validator = Draft7Validator(self.episode_schema, resolver=RefResolver.from_schema(self.schema))

        self.segment_schema = self.schema["$defs"]["Segment"]
        self.segment_validator = Draft7Validator(self.segment_schema, resolver=RefResolver.from_schema(self.schema))

        self.devices_schema = self.schema["properties"]["devices"]
        self.devices_validator = Draft7Validator(self.devices_schema, resolver=RefResolver.from_schema(self.schema))

    def initialize_metadata_callback(self, request, response):
        self.metadata_json_pub.publish(String(data=self._metadata_json()))  # publish current metadata before re-initializing
        self.metadata = self.__initialize_metadata()
        response.success = True
        response.message = "Metadata initialized."
        return response

    def set_episode_uuid_callback(self, request: StringTrigger.Request, response: StringTrigger.Response):
        episode_uuid = request.message.strip() if request.message else ""
        if not episode_uuid:
            response.success = False
            response.message = "Episode UUID validation error: uuid must not be empty."
            return response
        self.metadata.uuid = episode_uuid
        response.success = True
        response.message = "Episode UUID set in metadata."
        self.metadata_json_pub.publish(String(data=self._metadata_json()))
        return response

    def __initialize_metadata(self):
        # Clear the operator-selected task alongside the metadata so a new episode
        # never inherits the previous episode's task.
        self.task = None
        return MetadataV2_0(uuid=f"{uuid_mod.uuid4()}-local")

    def _metadata_json(self) -> str:
        """Serialize metadata, merging the operator-selected ``task`` (if any).

        ``MetadataV2_0.to_json()`` only emits the schema-defined fields, so the
        ``task`` object is spliced in as a top-level key here. The V2.0 schema
        permits extra top-level properties, so this still passes verification.
        """
        if self.task is None:
            return self.metadata.to_json()
        data = json.loads(self.metadata.to_json())
        data["task"] = self.task
        return json.dumps(data, ensure_ascii=False)

    def validate_and_respond(
        self,
        request_message: str,
        validator: Draft7Validator,
        success_msg: str,
        failure_prefix: str,
        response,  # Trigger.Response or StringTrigger.Response (duck-typed)
    ) -> Tuple[dict, object]:
        try:
            request_dict = json.loads(request_message)
            validator.validate(request_dict)
            response.success = True
            response.message = success_msg
            return request_dict, response
        except json.JSONDecodeError:
            request_dict = None
            response.success = False
            response.message = f"{failure_prefix}: Invalid JSON format."
        except exceptions.ValidationError as e:
            response.success = False
            response.message = f"{failure_prefix}: {e.message}"

        return request_dict, response

    def add_file_callback(self, request: StringTrigger.Request, response: StringTrigger.Response):
        request_dict, response = self.validate_and_respond(
            request.message, self.file_validator, "File added to metadata.", "File validation error", response
        )
        if request_dict:
            self.metadata.files.append(FileV2_0(**request_dict))

        self.metadata_json_pub.publish(String(data=self._metadata_json()))

        return response

    def set_robot_callback(self, request: StringTrigger.Request, response: StringTrigger.Response):
        request_dict, response = self.validate_and_respond(
            request.message, self.robot_validator, "Robot set in metadata.", "Robot validation error", response
        )
        if request_dict:
            self.metadata.robot = RobotV2_0(**request_dict)

        self.metadata_json_pub.publish(String(data=self._metadata_json()))

        return response

    def set_environment_callback(self, request: StringTrigger.Request, response: StringTrigger.Response):
        request_dict, response = self.validate_and_respond(
            request.message,
            self.environment_validator,
            "Environment set in metadata.",
            "Environment validation error",
            response,
        )
        if request_dict:
            self.metadata.environment = EnvironmentV2_0(**request_dict)

        self.metadata_json_pub.publish(String(data=self._metadata_json()))

        return response

    def set_runner_callback(self, request: StringTrigger.Request, response: StringTrigger.Response):
        request_dict, response = self.validate_and_respond(
            request.message, self.runner_validator, "Runner set in metadata.", "Runner validation error", response
        )
        if request_dict:
            self.metadata.runner = RunnerV2_0(**request_dict)

        self.metadata_json_pub.publish(String(data=self._metadata_json()))

        return response

    def set_devices_callback(self, request: StringTrigger.Request, response: StringTrigger.Response):
        request_dict, response = self.validate_and_respond(
            request.message, self.devices_validator, "Devices set in metadata.", "Devices validation error", response
        )
        if request_dict:
            self.metadata.devices = [DeviceV2_0(**d) for d in request_dict]

        self.metadata_json_pub.publish(String(data=self._metadata_json()))

        return response

    def add_program_callback(self, request: StringTrigger.Request, response: StringTrigger.Response):
        request_dict, response = self.validate_and_respond(
            request.message,
            self.program_validator,
            "Program added to metadata.",
            "Program validation error",
            response,
        )
        if request_dict:
            source_dict = request_dict.pop("source", None)
            source = SourceV2_0(**source_dict) if isinstance(source_dict, dict) and source_dict else SourceV2_0()
            self.metadata.programs.append(ProgramV2_0(**request_dict, source=source))

        self.metadata_json_pub.publish(String(data=self._metadata_json()))

        return response

    def extend_programs_callback(self, request: StringTrigger.Request, response: StringTrigger.Response):
        request_dict, response = self.validate_and_respond(
            request.message,
            self.programs_validator,
            "Programs extended in metadata.",
            "Programs validation error",
            response,
        )
        if request_dict:
            for p in request_dict:
                source_dict = p.pop("source", None)
                source = SourceV2_0(**source_dict) if isinstance(source_dict, dict) and source_dict else SourceV2_0()
                self.metadata.programs.append(ProgramV2_0(**p, source=source))

        self.metadata_json_pub.publish(String(data=self._metadata_json()))

        return response

    def add_label_callback(self, request: StringTrigger.Request, response: StringTrigger.Response):
        label = request.message
        if not label or not label.strip():
            response.success = False
            response.message = "Label validation error: label must not be empty."
            return response
        self.metadata.labels.append(label)
        response.success = True
        response.message = "Label added to metadata."
        self.metadata_json_pub.publish(String(data=self._metadata_json()))
        return response

    def set_episode_callback(self, request: StringTrigger.Request, response: StringTrigger.Response):
        request_dict, response = self.validate_and_respond(
            request.message, self.episode_validator, "Episode set in metadata.", "Episode validation error", response
        )
        if request_dict:
            self.metadata.episode = EpisodeV2_0(**request_dict)

        self.metadata_json_pub.publish(String(data=self._metadata_json()))

        return response

    def set_task_callback(self, request: StringTrigger.Request, response: StringTrigger.Response):
        """Set the operator-selected task for the current episode.

        Payload is a JSON object ``{"id": "<slug>", "instruction": "<text>"}``.
        ``id`` is the routing slug stamped into the object key (``task=<id>``);
        ``instruction`` is the free-text language string (optional). Stored
        outside the strict V2.0 dataclass and spliced into meta.json by
        ``_metadata_json``.
        """
        try:
            request_dict = json.loads(request.message)
        except json.JSONDecodeError:
            response.success = False
            response.message = "Task validation error: Invalid JSON format."
            return response

        if not isinstance(request_dict, dict):
            response.success = False
            response.message = "Task validation error: expected a JSON object."
            return response

        task_id = request_dict.get("id")
        if not isinstance(task_id, str) or not task_id.strip():
            response.success = False
            response.message = "Task validation error: 'id' must be a non-empty string."
            return response

        task = {"id": task_id.strip()}
        instruction = request_dict.get("instruction")
        if isinstance(instruction, str) and instruction.strip():
            task["instruction"] = instruction.strip()
        self.task = task

        response.success = True
        response.message = "Task set in metadata."
        self.metadata_json_pub.publish(String(data=self._metadata_json()))
        return response

    def add_segment_callback(self, request: StringTrigger.Request, response: StringTrigger.Response):
        request_dict, response = self.validate_and_respond(
            request.message, self.segment_validator, "Segment added to metadata.", "Segment validation error", response
        )
        if request_dict:
            self.metadata.segments.append(SegmentV2_0(**request_dict))

        self.metadata_json_pub.publish(String(data=self._metadata_json()))

        return response

    def remove_last_segment_callback(self, request: Trigger.Request, response: Trigger.Response):
        if self.metadata.segments:
            self.metadata.segments.pop()
            response.success = True
            response.message = "Last segment removed from metadata."
        else:
            response.success = False
            response.message = "No segments to remove from metadata."

        self.metadata_json_pub.publish(String(data=self._metadata_json()))
        return response

    def override_last_segment_success(self, request: StringTrigger.Request, response: StringTrigger.Response):
        if self.metadata.segments:
            self.metadata.segments[-1].success = request.message.lower() == "true"
            response.success = True
            response.message = "Last segment success status updated."
        else:
            response.success = False
            response.message = "No segments to update in metadata."

        self.metadata_json_pub.publish(String(data=self._metadata_json()))
        return response

    def get_verified_metadata_callback(self, request: Trigger.Request, response: Trigger.Response):
        metadata_str = self._metadata_json()
        _, response = self.validate_and_respond(
            metadata_str,
            self.schema_validator,
            "Metajson verified successfully.",
            "Metajson validation error",
            response,
        )
        if response.success:
            response.message = metadata_str
        return response

    def process_step(self):
        # publish metadata periodically
        self.metadata_json_pub.publish(String(data=self._metadata_json()))


def main():
    from yubi_core.sentry_setup import init_sentry
    init_sentry()
    rclpy.init()
    node = MetadataV2Handler()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        print("Keyboard interrupt received, shutting down metadata v2 handler.")
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == "__main__":
    main()
