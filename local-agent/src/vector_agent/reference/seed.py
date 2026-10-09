"""Unverified starter reference claims and explicitly marked synthetic test fixtures.

Policies:
- Source locators are unverified citations, not proof that they support each claim.
- No scraped copyrighted documentation; only factual specification properties.
- Synthetic fixtures are strictly labeled with is_synthetic=True and SourceClassification.SYNTHETIC_FIXTURE.
- Coverage inventory reports real-world coverage gaps honestly.
"""

from __future__ import annotations

from typing import Any

from vector_agent.models.component import ComponentKind
from vector_agent.models.reference import (
    CATALOG_SCHEMA_VERSION,
    SourceClassification,
)

from .catalog import ReferenceCatalog
from .importer import import_catalog_payload


def build_seed_payload() -> dict[str, Any]:
    """Construct a validated vector-catalog-v1 seed dictionary."""
    return {
        "schema_version": CATALOG_SCHEMA_VERSION,
        "sources": [
            # 1. Google Sources
            {
                "source_id": "google-support-portal",
                "title": "Google Hardware Support & Device Documentation",
                "publisher": "Google LLC",
                "url_or_document_id": "https://support.google.com/pixelphone",
                "source_classification": SourceClassification.OEM_DOCUMENTATION.value,
                "publication_date": None,
                "retrieved_at": None,
                "version_or_revision": None,
                "license_or_usage_constraints": None,
                "provenance_notes": "Unverified seed citation; retrieval, revision, publication date and claim support have not been established.",
                "is_synthetic": False,
            },
            {
                "source_id": "google-pixel7pro-specs",
                "title": "Pixel 7 Pro Technical Specifications",
                "publisher": "Google LLC",
                "url_or_document_id": "https://support.google.com/pixelphone/answer/7158570",
                "source_classification": SourceClassification.OEM_DOCUMENTATION.value,
                "publication_date": None,
                "retrieved_at": None,
                "version_or_revision": None,
                "license_or_usage_constraints": None,
                "provenance_notes": "Unverified seed citation; retrieval, revision, publication date and claim support have not been established.",
                "is_synthetic": False,
            },
            {
                "source_id": "fcc-pixel7pro-ge2ae",
                "title": "FCC Grant of Equipment Authorization - A4RGE2AE",
                "publisher": "Federal Communications Commission (FCC)",
                "url_or_document_id": "FCC-ID-A4RGE2AE",
                "source_classification": SourceClassification.REGULATORY_FILING.value,
                "publication_date": None,
                "retrieved_at": None,
                "version_or_revision": None,
                "license_or_usage_constraints": None,
                "provenance_notes": "Unverified seed citation; retrieval, revision, publication date and claim support have not been established.",
                "is_synthetic": False,
            },
            # 2. Samsung Sources
            {
                "source_id": "samsung-support-portal",
                "title": "Samsung Electronics Official Specifications",
                "publisher": "Samsung Electronics Co., Ltd.",
                "url_or_document_id": "https://www.samsung.com/global/galaxy/",
                "source_classification": SourceClassification.OEM_DOCUMENTATION.value,
                "publication_date": None,
                "retrieved_at": None,
                "version_or_revision": None,
                "license_or_usage_constraints": None,
                "provenance_notes": "Unverified seed citation; retrieval, revision, publication date and claim support have not been established.",
                "is_synthetic": False,
            },
            {
                "source_id": "samsung-s23ultra-specs",
                "title": "Galaxy S23 Ultra Tech Specs",
                "publisher": "Samsung Electronics Co., Ltd.",
                "url_or_document_id": "https://www.samsung.com/global/galaxy/galaxy-s23-ultra/specs/",
                "source_classification": SourceClassification.OEM_DOCUMENTATION.value,
                "publication_date": None,
                "retrieved_at": None,
                "version_or_revision": None,
                "license_or_usage_constraints": None,
                "provenance_notes": "Unverified seed citation; retrieval, revision, publication date and claim support have not been established.",
                "is_synthetic": False,
            },
            # 3. Apple Sources
            {
                "source_id": "apple-support-portal",
                "title": "Apple Support Technical Specifications",
                "publisher": "Apple Inc.",
                "url_or_document_id": "https://support.apple.com/specs",
                "source_classification": SourceClassification.OEM_DOCUMENTATION.value,
                "publication_date": None,
                "retrieved_at": None,
                "version_or_revision": None,
                "license_or_usage_constraints": None,
                "provenance_notes": "Unverified seed citation; retrieval, revision, publication date and claim support have not been established.",
                "is_synthetic": False,
            },
            {
                "source_id": "apple-iphone14pro-specs",
                "title": "iPhone 14 Pro - Technical Specifications",
                "publisher": "Apple Inc.",
                "url_or_document_id": "https://support.apple.com/kb/SP875",
                "source_classification": SourceClassification.OEM_DOCUMENTATION.value,
                "publication_date": None,
                "retrieved_at": None,
                "version_or_revision": None,
                "license_or_usage_constraints": None,
                "provenance_notes": "Unverified seed citation; retrieval, revision, publication date and claim support have not been established.",
                "is_synthetic": False,
            },
            # 4. Explicit Synthetic Test Source
            {
                "source_id": "synthetic-test-source",
                "title": "Synthetic Test Device Specification Fixture",
                "publisher": "VECTOR Test Infrastructure",
                "url_or_document_id": "urn:vector:test:synthetic-source",
                "source_classification": SourceClassification.SYNTHETIC_FIXTURE.value,
                "publication_date": None,
                "retrieved_at": None,
                "version_or_revision": None,
                "license_or_usage_constraints": "Internal test fixture only; not an OEM claim.",
                "provenance_notes": "Synthetic fixture for unit testing and mutation tests.",
                "is_synthetic": True,
            },
        ],
        "manufacturers": [
            {
                "manufacturer_id": "google",
                "canonical_name": "Google",
                "aliases": ["google llc", "alphabet"],
                "source_id": "google-support-portal",
                "notes": "Manufacturer of Google Pixel smartphones.",
            },
            {
                "manufacturer_id": "samsung",
                "canonical_name": "Samsung",
                "aliases": ["samsung electronics", "samsung electronics co., ltd."],
                "source_id": "samsung-support-portal",
                "notes": "Manufacturer of Samsung Galaxy smartphones.",
            },
            {
                "manufacturer_id": "apple",
                "canonical_name": "Apple",
                "aliases": ["apple inc", "apple computer"],
                "source_id": "apple-support-portal",
                "notes": "Manufacturer of iPhone devices.",
            },
            {
                "manufacturer_id": "synthetic-mfg",
                "canonical_name": "Synthetic Mobile Inc",
                "aliases": ["synthetic-oem"],
                "source_id": "synthetic-test-source",
                "notes": "Synthetic test manufacturer.",
            },
        ],
        "models": [
            # Pixel 7 Pro
            {
                "model_id": "pixel-7-pro",
                "manufacturer_id": "google",
                "marketed_name": "Pixel 7 Pro",
                "model_family": "Pixel",
                "generation": "7",
                "known_model_codes": ["ge2ae", "gp4bc"],
                "device_codenames": ["cheetah"],
                "source_ids": ["google-pixel7pro-specs"],
                "base_specifications": None,
                "supported_component_alternatives": [
                    {
                        "component_kind": ComponentKind.BATTERY.value,
                        "component_role": "battery-pack",
                        "part_number": "G1000",
                        "documented_suppliers": ["Sunwoda", "ATL"],
                        "supported_properties": {"rated_capacity_mah": 4926},
                        "source_id": "fcc-pixel7pro-ge2ae",
                        "notes": "Documented dual suppliers in regulatory filings.",
                    }
                ],
            },
            # Galaxy S23 Ultra
            {
                "model_id": "galaxy-s23-ultra",
                "manufacturer_id": "samsung",
                "marketed_name": "Galaxy S23 Ultra",
                "model_family": "Galaxy S",
                "generation": "23",
                "known_model_codes": ["sm-s918u", "sm-s918b"],
                "device_codenames": ["dm3q"],
                "source_ids": ["samsung-s23ultra-specs"],
                "base_specifications": None,
                "supported_component_alternatives": [],
            },
            # iPhone 14 Pro
            {
                "model_id": "iphone-14-pro",
                "manufacturer_id": "apple",
                "marketed_name": "iPhone 14 Pro",
                "model_family": "iPhone",
                "generation": "14",
                "known_model_codes": ["a2650", "a2890"],
                "device_codenames": ["iphone15-2"],
                "source_ids": ["apple-iphone14pro-specs"],
                "base_specifications": None,
                "supported_component_alternatives": [],
            },
            # Synthetic Model
            {
                "model_id": "synthetic-model-x",
                "is_synthetic": True,
                "manufacturer_id": "synthetic-mfg",
                "marketed_name": "Synthetic Model X",
                "model_family": "Synthetic",
                "generation": "1",
                "known_model_codes": ["synth-x1"],
                "device_codenames": ["synthx"],
                "source_ids": ["synthetic-test-source"],
                "base_specifications": None,
                "supported_component_alternatives": [],
            },
        ],
        "variants": [
            # Pixel 7 Pro - US (GE2AE)
            {
                "variant_id": "pixel-7-pro-us-ge2ae",
                "model_id": "pixel-7-pro",
                "region_market": "US",
                "model_codes": ["ge2ae"],
                "sku_numbers": ["GA03462-US"],
                "hardware_revisions": ["MP1.0"],
                "network_configuration": "5G Sub-6 + mmWave",
                "specifications": {
                    "display": {
                        "technology": "LTPO AMOLED",
                        "size_diagonal_inches": 6.7,
                        "resolution_width": 1440,
                        "resolution_height": 3120,
                        "refresh_rate_max_hz": 120,
                        "refresh_rate_min_hz": 10,
                        "supported_refresh_rates": [10, 30, 60, 120],
                        "pixel_density_ppi": 512,
                        "hdr_standards": ["HDR10", "HDR10+"],
                    },
                    "battery": {
                        "rated_capacity_mah": 4926,
                        "typical_capacity_mah": 5000,
                        "chemistry": "Li-ion",
                        "nominal_voltage_mv": 3870,
                        "max_charging_wattage_wired": 30.0,
                        "wireless_charging_supported": True,
                        "max_charging_wattage_wireless": 23.0,
                        "removable": False,
                    },
                    "soc": {
                        "chip_maker": "Google",
                        "marketing_name": "Google Tensor G2",
                        "part_number": "GS201",
                        "cpu_architecture": "arm64-v8a",
                        "core_count": 8,
                        "gpu_model": "Mali-G710 MP7",
                        "process_node_nm": 5,
                    },
                    "memory_storage": {
                        "ram_options_bytes": [12 * 1024**3],
                        "storage_options_bytes": [128 * 10**9, 256 * 10**9, 512 * 10**9],
                        "ram_type": "LPDDR5",
                        "storage_type": "UFS 3.1",
                        "expandable_storage": False,
                    },
                    "camera": {
                        "rear_cameras": [
                            {
                                "role": "primary",
                                "resolution_mp": 50.0,
                                "aperture_f_number": 1.85,
                                "focal_length_equiv_mm": 25.0,
                                "sensor_model": "Samsung ISOCELL GN1",
                                "optical_image_stabilization": True,
                                "autofocus_supported": True,
                            },
                            {
                                "role": "ultrawide",
                                "resolution_mp": 12.0,
                                "aperture_f_number": 2.2,
                                "focal_length_equiv_mm": 13.0,
                                "autofocus_supported": True,
                            },
                            {
                                "role": "telephoto",
                                "resolution_mp": 48.0,
                                "aperture_f_number": 3.5,
                                "focal_length_equiv_mm": 120.0,
                                "optical_image_stabilization": True,
                                "autofocus_supported": True,
                            },
                        ],
                        "front_cameras": [
                            {
                                "role": "front",
                                "resolution_mp": 10.8,
                                "aperture_f_number": 2.2,
                                "focal_length_equiv_mm": 21.0,
                                "autofocus_supported": False,
                            }
                        ],
                        "has_flash": True,
                        "lidar_or_tof_present": False,
                    },
                    "sensors": {
                        "fingerprint_type": "optical_under_display",
                        "accelerometer": True,
                        "gyroscope": True,
                        "magnetometer": True,
                        "barometer": True,
                        "proximity": True,
                        "ambient_light": True,
                        "nfc": True,
                        "ultra_wideband": True,
                    },
                    "connectivity": {
                        "wifi_generations": ["Wi-Fi 6E", "Wi-Fi 6"],
                        "bluetooth_version": "5.2",
                        "cellular_generations": ["4G", "5G"],
                        "usb_type": "USB-C",
                        "usb_version": "3.2 Gen 2",
                    },
                    "audio_haptics": {
                        "speaker_type": "stereo",
                        "headphone_jack_3_5mm": False,
                        "haptic_motor_type": "linear_resonant_actuator",
                    },
                    "source_ids": ["google-pixel7pro-specs", "fcc-pixel7pro-ge2ae"],
                },
                "supported_components": [],
                "source_ids": ["google-pixel7pro-specs", "fcc-pixel7pro-ge2ae"],
                "notes": "US model with 5G mmWave support.",
            },
            # Pixel 7 Pro - Global (GP4BC)
            {
                "variant_id": "pixel-7-pro-global-gp4bc",
                "model_id": "pixel-7-pro",
                "region_market": "Global",
                "model_codes": ["gp4bc"],
                "sku_numbers": ["GA03463-EU"],
                "hardware_revisions": ["MP1.0"],
                "network_configuration": "5G Sub-6",
                "specifications": {
                    "display": {
                        "technology": "LTPO AMOLED",
                        "size_diagonal_inches": 6.7,
                        "resolution_width": 1440,
                        "resolution_height": 3120,
                        "refresh_rate_max_hz": 120,
                        "refresh_rate_min_hz": 10,
                        "supported_refresh_rates": [10, 30, 60, 120],
                        "pixel_density_ppi": 512,
                        "hdr_standards": ["HDR10", "HDR10+"],
                    },
                    "battery": {
                        "rated_capacity_mah": 4926,
                        "typical_capacity_mah": 5000,
                        "chemistry": "Li-ion",
                        "nominal_voltage_mv": 3870,
                        "max_charging_wattage_wired": 30.0,
                        "wireless_charging_supported": True,
                        "max_charging_wattage_wireless": 23.0,
                        "removable": False,
                    },
                    "soc": {
                        "chip_maker": "Google",
                        "marketing_name": "Google Tensor G2",
                        "part_number": "GS201",
                        "cpu_architecture": "arm64-v8a",
                        "core_count": 8,
                        "gpu_model": "Mali-G710 MP7",
                        "process_node_nm": 5,
                    },
                    "memory_storage": {
                        "ram_options_bytes": [12 * 1024**3],
                        "storage_options_bytes": [128 * 10**9, 256 * 10**9, 512 * 10**9],
                        "ram_type": "LPDDR5",
                        "storage_type": "UFS 3.1",
                        "expandable_storage": False,
                    },
                    "camera": {
                        "rear_cameras": [
                            {
                                "role": "primary",
                                "resolution_mp": 50.0,
                                "aperture_f_number": 1.85,
                                "focal_length_equiv_mm": 25.0,
                                "sensor_model": "Samsung ISOCELL GN1",
                                "optical_image_stabilization": True,
                                "autofocus_supported": True,
                            },
                            {
                                "role": "ultrawide",
                                "resolution_mp": 12.0,
                                "aperture_f_number": 2.2,
                                "focal_length_equiv_mm": 13.0,
                                "autofocus_supported": True,
                            },
                            {
                                "role": "telephoto",
                                "resolution_mp": 48.0,
                                "aperture_f_number": 3.5,
                                "focal_length_equiv_mm": 120.0,
                                "optical_image_stabilization": True,
                                "autofocus_supported": True,
                            },
                        ],
                        "front_cameras": [
                            {
                                "role": "front",
                                "resolution_mp": 10.8,
                                "aperture_f_number": 2.2,
                                "focal_length_equiv_mm": 21.0,
                                "autofocus_supported": False,
                            }
                        ],
                        "has_flash": True,
                        "lidar_or_tof_present": False,
                    },
                    "sensors": {
                        "fingerprint_type": "optical_under_display",
                        "accelerometer": True,
                        "gyroscope": True,
                        "magnetometer": True,
                        "barometer": True,
                        "proximity": True,
                        "ambient_light": True,
                        "nfc": True,
                        "ultra_wideband": True,
                    },
                    "connectivity": {
                        "wifi_generations": ["Wi-Fi 6E", "Wi-Fi 6"],
                        "bluetooth_version": "5.2",
                        "cellular_generations": ["4G", "5G"],
                        "usb_type": "USB-C",
                        "usb_version": "3.2 Gen 2",
                    },
                    "audio_haptics": {
                        "speaker_type": "stereo",
                        "headphone_jack_3_5mm": False,
                        "haptic_motor_type": "linear_resonant_actuator",
                    },
                    "source_ids": ["google-pixel7pro-specs"],
                },
                "supported_components": [],
                "source_ids": ["google-pixel7pro-specs"],
                "notes": "Global model with 5G Sub-6.",
            },
            # Samsung Galaxy S23 Ultra - US (SM-S918U)
            {
                "variant_id": "galaxy-s23-ultra-us-s918u",
                "model_id": "galaxy-s23-ultra",
                "region_market": "US",
                "model_codes": ["sm-s918u"],
                "sku_numbers": ["SM-S918UZKAXAA"],
                "hardware_revisions": ["REV1.0"],
                "network_configuration": "5G Sub-6 + mmWave",
                "specifications": {
                    "display": {
                        "technology": "Dynamic AMOLED 2X",
                        "size_diagonal_inches": 6.8,
                        "resolution_width": 1440,
                        "resolution_height": 3088,
                        "refresh_rate_max_hz": 120,
                        "refresh_rate_min_hz": 1,
                        "supported_refresh_rates": [24, 60, 120],
                        "pixel_density_ppi": 500,
                        "hdr_standards": ["HDR10+"],
                    },
                    "battery": {
                        "rated_capacity_mah": 4855,
                        "typical_capacity_mah": 5000,
                        "chemistry": "Li-ion",
                        "nominal_voltage_mv": 3880,
                        "max_charging_wattage_wired": 45.0,
                        "wireless_charging_supported": True,
                        "max_charging_wattage_wireless": 15.0,
                        "removable": False,
                    },
                    "soc": {
                        "chip_maker": "Qualcomm",
                        "marketing_name": "Snapdragon 8 Gen 2 for Galaxy",
                        "part_number": "SM8550-AC",
                        "cpu_architecture": "arm64-v8a",
                        "core_count": 8,
                        "gpu_model": "Adreno 740",
                        "process_node_nm": 4,
                    },
                    "memory_storage": {
                        "ram_options_bytes": [8 * 1024**3, 12 * 1024**3],
                        "storage_options_bytes": [256 * 10**9, 512 * 10**9, 1024 * 10**9],
                        "ram_type": "LPDDR5X",
                        "storage_type": "UFS 4.0",
                        "expandable_storage": False,
                    },
                    "camera": {
                        "rear_cameras": [
                            {
                                "role": "primary",
                                "resolution_mp": 200.0,
                                "aperture_f_number": 1.7,
                                "focal_length_equiv_mm": 24.0,
                                "sensor_model": "Samsung ISOCELL HP2",
                                "optical_image_stabilization": True,
                                "autofocus_supported": True,
                            },
                            {
                                "role": "ultrawide",
                                "resolution_mp": 12.0,
                                "aperture_f_number": 2.2,
                                "focal_length_equiv_mm": 13.0,
                                "autofocus_supported": True,
                            },
                            {
                                "role": "telephoto_3x",
                                "resolution_mp": 10.0,
                                "aperture_f_number": 2.4,
                                "focal_length_equiv_mm": 70.0,
                                "optical_image_stabilization": True,
                                "autofocus_supported": True,
                            },
                            {
                                "role": "telephoto_10x",
                                "resolution_mp": 10.0,
                                "aperture_f_number": 4.9,
                                "focal_length_equiv_mm": 230.0,
                                "optical_image_stabilization": True,
                                "autofocus_supported": True,
                            },
                        ],
                        "front_cameras": [
                            {
                                "role": "front",
                                "resolution_mp": 12.0,
                                "aperture_f_number": 2.2,
                                "focal_length_equiv_mm": 26.0,
                                "autofocus_supported": True,
                            }
                        ],
                        "has_flash": True,
                        "lidar_or_tof_present": False,
                    },
                    "sensors": {
                        "fingerprint_type": "ultrasonic_under_display",
                        "accelerometer": True,
                        "gyroscope": True,
                        "magnetometer": True,
                        "barometer": True,
                        "proximity": True,
                        "ambient_light": True,
                        "nfc": True,
                        "ultra_wideband": True,
                    },
                    "connectivity": {
                        "wifi_generations": ["Wi-Fi 6E", "Wi-Fi 6"],
                        "bluetooth_version": "5.3",
                        "cellular_generations": ["4G", "5G"],
                        "usb_type": "USB-C",
                        "usb_version": "3.2 Gen 1",
                    },
                    "audio_haptics": {
                        "speaker_type": "stereo",
                        "headphone_jack_3_5mm": False,
                    },
                    "source_ids": ["samsung-s23ultra-specs"],
                },
                "supported_components": [],
                "source_ids": ["samsung-s23ultra-specs"],
                "notes": "US model with 5G mmWave support.",
            },
            # Samsung Galaxy S23 Ultra - Global (SM-S918B)
            {
                "variant_id": "galaxy-s23-ultra-global-s918b",
                "model_id": "galaxy-s23-ultra",
                "region_market": "Global",
                "model_codes": ["sm-s918b"],
                "sku_numbers": ["SM-S918BZKDEUE"],
                "hardware_revisions": ["REV1.0"],
                "network_configuration": "5G Sub-6",
                "specifications": {
                    "display": {
                        "technology": "Dynamic AMOLED 2X",
                        "size_diagonal_inches": 6.8,
                        "resolution_width": 1440,
                        "resolution_height": 3088,
                        "refresh_rate_max_hz": 120,
                        "refresh_rate_min_hz": 1,
                        "supported_refresh_rates": [24, 60, 120],
                        "pixel_density_ppi": 500,
                        "hdr_standards": ["HDR10+"],
                    },
                    "battery": {
                        "rated_capacity_mah": 4855,
                        "typical_capacity_mah": 5000,
                        "chemistry": "Li-ion",
                        "nominal_voltage_mv": 3880,
                        "max_charging_wattage_wired": 45.0,
                        "wireless_charging_supported": True,
                        "max_charging_wattage_wireless": 15.0,
                        "removable": False,
                    },
                    "soc": {
                        "chip_maker": "Qualcomm",
                        "marketing_name": "Snapdragon 8 Gen 2 for Galaxy",
                        "part_number": "SM8550-AC",
                        "cpu_architecture": "arm64-v8a",
                        "core_count": 8,
                        "gpu_model": "Adreno 740",
                        "process_node_nm": 4,
                    },
                    "memory_storage": {
                        "ram_options_bytes": [8 * 1024**3, 12 * 1024**3],
                        "storage_options_bytes": [256 * 10**9, 512 * 10**9, 1024 * 10**9],
                        "ram_type": "LPDDR5X",
                        "storage_type": "UFS 4.0",
                        "expandable_storage": False,
                    },
                    "camera": {
                        "rear_cameras": [
                            {
                                "role": "primary",
                                "resolution_mp": 200.0,
                                "aperture_f_number": 1.7,
                                "focal_length_equiv_mm": 24.0,
                                "sensor_model": "Samsung ISOCELL HP2",
                                "optical_image_stabilization": True,
                                "autofocus_supported": True,
                            },
                            {
                                "role": "ultrawide",
                                "resolution_mp": 12.0,
                                "aperture_f_number": 2.2,
                                "focal_length_equiv_mm": 13.0,
                                "autofocus_supported": True,
                            },
                            {
                                "role": "telephoto_3x",
                                "resolution_mp": 10.0,
                                "aperture_f_number": 2.4,
                                "focal_length_equiv_mm": 70.0,
                                "optical_image_stabilization": True,
                                "autofocus_supported": True,
                            },
                            {
                                "role": "telephoto_10x",
                                "resolution_mp": 10.0,
                                "aperture_f_number": 4.9,
                                "focal_length_equiv_mm": 230.0,
                                "optical_image_stabilization": True,
                                "autofocus_supported": True,
                            },
                        ],
                        "front_cameras": [
                            {
                                "role": "front",
                                "resolution_mp": 12.0,
                                "aperture_f_number": 2.2,
                                "focal_length_equiv_mm": 26.0,
                                "autofocus_supported": True,
                            }
                        ],
                        "has_flash": True,
                        "lidar_or_tof_present": False,
                    },
                    "sensors": {
                        "fingerprint_type": "ultrasonic_under_display",
                        "accelerometer": True,
                        "gyroscope": True,
                        "magnetometer": True,
                        "barometer": True,
                        "proximity": True,
                        "ambient_light": True,
                        "nfc": True,
                        "ultra_wideband": True,
                    },
                    "connectivity": {
                        "wifi_generations": ["Wi-Fi 6E", "Wi-Fi 6"],
                        "bluetooth_version": "5.3",
                        "cellular_generations": ["4G", "5G"],
                        "usb_type": "USB-C",
                        "usb_version": "3.2 Gen 1",
                    },
                    "audio_haptics": {
                        "speaker_type": "stereo",
                        "headphone_jack_3_5mm": False,
                    },
                    "source_ids": ["samsung-s23ultra-specs"],
                },
                "supported_components": [],
                "source_ids": ["samsung-s23ultra-specs"],
                "notes": "Global model.",
            },
            # Apple iPhone 14 Pro - US (A2650)
            {
                "variant_id": "iphone-14-pro-us-a2650",
                "model_id": "iphone-14-pro",
                "region_market": "US",
                "model_codes": ["a2650"],
                "sku_numbers": ["MQ023LL/A"],
                "hardware_revisions": [],
                "network_configuration": "5G Sub-6 + mmWave",
                "specifications": {
                    "display": {
                        "technology": "Super Retina XDR OLED",
                        "size_diagonal_inches": 6.1,
                        "resolution_width": 1179,
                        "resolution_height": 2556,
                        "refresh_rate_max_hz": 120,
                        "refresh_rate_min_hz": 1,
                        "supported_refresh_rates": [10, 24, 30, 60, 120],
                        "pixel_density_ppi": 460,
                        "hdr_standards": ["HDR10", "Dolby Vision"],
                    },
                    "battery": {
                        "rated_capacity_mah": 3200,
                        "typical_capacity_mah": 3200,
                        "chemistry": "Li-ion",
                        "nominal_voltage_mv": 3870,
                        "max_charging_wattage_wired": 20.0,
                        "wireless_charging_supported": True,
                        "max_charging_wattage_wireless": 15.0,
                        "removable": False,
                    },
                    "soc": {
                        "chip_maker": "Apple",
                        "marketing_name": "Apple A16 Bionic",
                        "part_number": "APL1W10",
                        "cpu_architecture": "arm64-v8a",
                        "core_count": 6,
                        "gpu_model": "Apple 5-core GPU",
                        "process_node_nm": 4,
                    },
                    "memory_storage": {
                        "ram_options_bytes": [6 * 1024**3],
                        "storage_options_bytes": [
                            128 * 10**9,
                            256 * 10**9,
                            512 * 10**9,
                            1024 * 10**9,
                        ],
                        "ram_type": "LPDDR5",
                        "storage_type": "NVMe",
                        "expandable_storage": False,
                    },
                    "camera": {
                        "rear_cameras": [
                            {
                                "role": "primary",
                                "resolution_mp": 48.0,
                                "aperture_f_number": 1.78,
                                "focal_length_equiv_mm": 24.0,
                                "optical_image_stabilization": True,
                                "autofocus_supported": True,
                            },
                            {
                                "role": "ultrawide",
                                "resolution_mp": 12.0,
                                "aperture_f_number": 2.2,
                                "focal_length_equiv_mm": 13.0,
                                "autofocus_supported": True,
                            },
                            {
                                "role": "telephoto",
                                "resolution_mp": 12.0,
                                "aperture_f_number": 2.8,
                                "focal_length_equiv_mm": 77.0,
                                "optical_image_stabilization": True,
                                "autofocus_supported": True,
                            },
                        ],
                        "front_cameras": [
                            {
                                "role": "front",
                                "resolution_mp": 12.0,
                                "aperture_f_number": 1.9,
                                "focal_length_equiv_mm": 23.0,
                                "autofocus_supported": True,
                            }
                        ],
                        "has_flash": True,
                        "lidar_or_tof_present": True,
                    },
                    "sensors": {
                        "fingerprint_type": None,
                        "accelerometer": True,
                        "gyroscope": True,
                        "magnetometer": True,
                        "barometer": True,
                        "proximity": True,
                        "ambient_light": True,
                        "nfc": True,
                        "ultra_wideband": True,
                    },
                    "connectivity": {
                        "wifi_generations": ["Wi-Fi 6"],
                        "bluetooth_version": "5.3",
                        "cellular_generations": ["4G", "5G"],
                        "usb_type": "Lightning",
                        "usb_version": "2.0",
                    },
                    "audio_haptics": {
                        "speaker_type": "stereo",
                        "headphone_jack_3_5mm": False,
                        "haptic_motor_type": "taptic_engine",
                    },
                    "source_ids": ["apple-iphone14pro-specs"],
                },
                "supported_components": [],
                "source_ids": ["apple-iphone14pro-specs"],
                "notes": "US model with eSIM only and mmWave.",
            },
            # Apple iPhone 14 Pro - Global (A2890)
            {
                "variant_id": "iphone-14-pro-global-a2890",
                "model_id": "iphone-14-pro",
                "region_market": "Global",
                "model_codes": ["a2890"],
                "sku_numbers": ["MPXV3ZD/A"],
                "hardware_revisions": [],
                "network_configuration": "5G Sub-6",
                "specifications": {
                    "display": {
                        "technology": "Super Retina XDR OLED",
                        "size_diagonal_inches": 6.1,
                        "resolution_width": 1179,
                        "resolution_height": 2556,
                        "refresh_rate_max_hz": 120,
                        "refresh_rate_min_hz": 1,
                        "supported_refresh_rates": [10, 24, 30, 60, 120],
                        "pixel_density_ppi": 460,
                        "hdr_standards": ["HDR10", "Dolby Vision"],
                    },
                    "battery": {
                        "rated_capacity_mah": 3200,
                        "typical_capacity_mah": 3200,
                        "chemistry": "Li-ion",
                        "nominal_voltage_mv": 3870,
                        "max_charging_wattage_wired": 20.0,
                        "wireless_charging_supported": True,
                        "max_charging_wattage_wireless": 15.0,
                        "removable": False,
                    },
                    "soc": {
                        "chip_maker": "Apple",
                        "marketing_name": "Apple A16 Bionic",
                        "part_number": "APL1W10",
                        "cpu_architecture": "arm64-v8a",
                        "core_count": 6,
                        "gpu_model": "Apple 5-core GPU",
                        "process_node_nm": 4,
                    },
                    "memory_storage": {
                        "ram_options_bytes": [6 * 1024**3],
                        "storage_options_bytes": [
                            128 * 10**9,
                            256 * 10**9,
                            512 * 10**9,
                            1024 * 10**9,
                        ],
                        "ram_type": "LPDDR5",
                        "storage_type": "NVMe",
                        "expandable_storage": False,
                    },
                    "camera": {
                        "rear_cameras": [
                            {
                                "role": "primary",
                                "resolution_mp": 48.0,
                                "aperture_f_number": 1.78,
                                "focal_length_equiv_mm": 24.0,
                                "sensor_model": "Sony Exmor RS",
                                "optical_image_stabilization": True,
                                "autofocus_supported": True,
                            },
                            {
                                "role": "ultrawide",
                                "resolution_mp": 12.0,
                                "aperture_f_number": 2.2,
                                "focal_length_equiv_mm": 13.0,
                                "autofocus_supported": True,
                            },
                            {
                                "role": "telephoto",
                                "resolution_mp": 12.0,
                                "aperture_f_number": 2.8,
                                "focal_length_equiv_mm": 77.0,
                                "optical_image_stabilization": True,
                                "autofocus_supported": True,
                            },
                        ],
                        "front_cameras": [
                            {
                                "role": "front",
                                "resolution_mp": 12.0,
                                "aperture_f_number": 1.9,
                                "focal_length_equiv_mm": 23.0,
                                "autofocus_supported": True,
                            }
                        ],
                        "has_flash": True,
                        "lidar_or_tof_present": True,
                    },
                    "sensors": {
                        "fingerprint_type": None,
                        "accelerometer": True,
                        "gyroscope": True,
                        "magnetometer": True,
                        "barometer": True,
                        "proximity": True,
                        "ambient_light": True,
                        "nfc": True,
                        "ultra_wideband": True,
                    },
                    "connectivity": {
                        "wifi_generations": ["Wi-Fi 6"],
                        "bluetooth_version": "5.3",
                        "cellular_generations": ["4G", "5G"],
                        "usb_type": "Lightning",
                        "usb_version": "2.0",
                    },
                    "audio_haptics": {
                        "speaker_type": "stereo",
                        "headphone_jack_3_5mm": False,
                        "haptic_motor_type": "taptic_engine",
                    },
                    "source_ids": ["apple-iphone14pro-specs"],
                },
                "supported_components": [],
                "source_ids": ["apple-iphone14pro-specs"],
                "notes": "Global model with physical SIM slot.",
            },
            # Synthetic Variant
            {
                "variant_id": "synthetic-variant-x",
                "model_id": "synthetic-model-x",
                "region_market": "Global",
                "model_codes": ["synth-x1"],
                "sku_numbers": [],
                "hardware_revisions": [],
                "network_configuration": "5G",
                "specifications": {
                    "display": {
                        "technology": "IPS LCD",
                        "resolution_width": 1080,
                        "resolution_height": 2400,
                        "refresh_rate_max_hz": 90,
                        "supported_refresh_rates": [60, 90],
                    },
                    "battery": {
                        "rated_capacity_mah": 4500,
                        "typical_capacity_mah": 4500,
                    },
                    "soc": {
                        "chip_maker": "SyntheticChip",
                        "marketing_name": "Synthetic 100",
                        "cpu_architecture": "arm64-v8a",
                        "core_count": 8,
                    },
                    "memory_storage": {
                        "ram_options_bytes": [4 * 1024**3],
                        "storage_options_bytes": [64 * 10**9],
                    },
                    "source_ids": ["synthetic-test-source"],
                },
                "supported_components": [],
                "source_ids": ["synthetic-test-source"],
                "notes": "Synthetic variant fixture.",
            },
        ],
        "conflicts": [],
        "performance_metrics": [],
    }


def build_seed_catalog(*, test_only: bool = False) -> ReferenceCatalog:
    """Build and populate a ReferenceCatalog instance with the unverified starter dataset."""
    catalog = ReferenceCatalog(test_only=test_only)
    payload = build_seed_payload()
    if not test_only:
        payload["sources"] = [s for s in payload["sources"] if not s["is_synthetic"]]
        payload["manufacturers"] = [
            m for m in payload["manufacturers"] if m["manufacturer_id"] != "synthetic-mfg"
        ]
        payload["models"] = [m for m in payload["models"] if not m.get("is_synthetic", False)]
        ids = {m["model_id"] for m in payload["models"]}
        payload["variants"] = [v for v in payload["variants"] if v["model_id"] in ids]
    import_catalog_payload(payload, catalog)
    return catalog


def get_coverage_inventory(catalog: ReferenceCatalog | None = None) -> dict[str, Any]:
    """Report real-world vs synthetic coverage gaps honestly."""
    cat = catalog or build_seed_catalog()
    sources = cat.all_sources()
    models = cat.all_models()
    variants = cat.all_variants()

    catalogued_models = [
        m.marketed_name
        for m in models
        if not any(cat.get_source(sid) and cat.get_source(sid).is_synthetic for sid in m.source_ids)  # type: ignore[union-attr]
    ]
    synthetic_models = [m.marketed_name for m in models if m.marketed_name not in catalogued_models]

    return {
        "status": "UNVERIFIED_STARTER_DATASET",
        "verified_devices_count": 0,
        "verified_device_models": [],
        "unverified_device_models": catalogued_models,
        "synthetic_fixtures_count": len(synthetic_models),
        "synthetic_models": synthetic_models,
        "total_variants_count": len(variants),
        "total_sources_count": len(sources),
        "coverage_limitation_statement": (
            "Current catalog contains starter seed data for Google Pixel 7 Pro, "
            "Samsung Galaxy S23 Ultra, and Apple iPhone 14 Pro with unverified source locators. "
            "Broad production coverage requires continued importation under Phase 8E rules. "
            "Claim-level verification and catalog-integrity corrections remain open. No verified performance baselines are loaded."
        ),
    }
