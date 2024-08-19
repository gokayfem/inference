from typing import Any, DefaultDict, Dict, List, Optional, Union

ResourceID = str
Usage = Union[DefaultDict[str, Any], Dict[str, Any]]
ResourceUsage = Union[DefaultDict[ResourceID, Usage], Dict[ResourceID, Usage]]
APIKey = str
APIKeyHash = str
APIKeyUsage = Union[DefaultDict[APIKey, ResourceUsage], Dict[APIKey, ResourceUsage]]
ResourceDetails = Dict[str, Any]
SystemDetails = Dict[str, Any]
UsagePayload = Union[APIKeyUsage, ResourceDetails, SystemDetails]


def merge_usage_dicts(d1: UsagePayload, d2: UsagePayload):
    merged = {}
    if d1 and d2 and d1.get("resource_id") != d2.get("resource_id"):
        raise ValueError("Cannot merge usage for different resource IDs")
    if "timestamp_start" in d1 and "timestamp_start" in d2:
        merged["timestamp_start"] = min(d1["timestamp_start"], d2["timestamp_start"])
    if "timestamp_stop" in d1 and "timestamp_stop" in d2:
        merged["timestamp_stop"] = max(d1["timestamp_stop"], d2["timestamp_stop"])
    if "processed_frames" in d1 and "processed_frames" in d2:
        merged["processed_frames"] = d1["processed_frames"] + d2["processed_frames"]
    if "source_duration" in d1 and "source_duration" in d2:
        merged["source_duration"] = d1["source_duration"] + d2["source_duration"]
    return {**d1, **d2, **merged}


def get_api_key_usage_containing_resource(
    api_key_hash: APIKey, usage_payloads: List[APIKeyUsage]
) -> Optional[ResourceUsage]:
    for usage_payload in usage_payloads:
        for other_api_key_hash, resource_payloads in usage_payload.items():
            if api_key_hash and other_api_key_hash != api_key_hash:
                continue
            if other_api_key_hash == "":
                continue
            for resource_id, resource_usage in resource_payloads.items():
                if not resource_id:
                    continue
                if not resource_usage or "resource_id" not in resource_usage:
                    continue
                return resource_usage
    return


def zip_usage_payloads(usage_payloads: List[APIKeyUsage]) -> List[APIKeyUsage]:
    merged_api_key_usage_payloads: APIKeyUsage = {}
    system_info_payload = None
    for usage_payload in usage_payloads:
        for api_key_hash, resource_payloads in usage_payload.items():
            if api_key_hash == "":
                if (
                    resource_payloads
                    and len(resource_payloads) > 1
                    or list(resource_payloads.keys()) != [""]
                ):
                    continue
                api_key_usage_with_resource = get_api_key_usage_containing_resource(
                    api_key_hash=api_key_hash,
                    usage_payloads=usage_payloads,
                )
                if not api_key_usage_with_resource:
                    system_info_payload = resource_payloads
                    continue
                api_key_hash = api_key_usage_with_resource["api_key_hash"]
                resource_id = api_key_usage_with_resource["resource_id"]
                category = api_key_usage_with_resource.get("category")
                for v in resource_payloads.values():
                    v["api_key_hash"] = api_key_hash
                    if "resource_id" not in v or not v["resource_id"]:
                        v["resource_id"] = resource_id
                    if "category" not in v or not v["category"]:
                        v["category"] = category
            for (
                resource_usage_key,
                resource_usage_payload,
            ) in resource_payloads.items():
                if resource_usage_key == "":
                    api_key_usage_with_resource = get_api_key_usage_containing_resource(
                        api_key_hash=api_key_hash,
                        usage_payloads=usage_payloads,
                    )
                    if not api_key_usage_with_resource:
                        system_info_payload = {"": resource_usage_payload}
                        continue
                    resource_id = api_key_usage_with_resource["resource_id"]
                    category = api_key_usage_with_resource.get("category")
                    resource_usage_key = f"{category}:{resource_id}"
                    resource_usage_payload["api_key_hash"] = api_key_hash
                    resource_usage_payload["resource_id"] = resource_id
                    resource_usage_payload["category"] = category
                merged_api_key_payload = merged_api_key_usage_payloads.setdefault(
                    api_key_hash, {}
                )
                merged_resource_payload = merged_api_key_payload.setdefault(
                    resource_usage_key, {}
                )
                merged_api_key_payload[resource_usage_key] = merge_usage_dicts(
                    merged_resource_payload,
                    resource_usage_payload,
                )

    zipped_payloads = [merged_api_key_usage_payloads]
    if system_info_payload:
        system_info_api_key_hash = next(iter(system_info_payload.values()))[
            "api_key_hash"
        ]
        zipped_payloads.append({system_info_api_key_hash: system_info_payload})
    return zipped_payloads
