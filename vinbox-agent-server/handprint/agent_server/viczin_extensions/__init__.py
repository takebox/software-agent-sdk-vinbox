"""Viczin Extensions: installable UI bundles that contribute pages to Viczin."""

from handprint.agent_server.viczin_extensions.installed import (
    ViczinExtensionUpdateCheck,
    InstalledViczinExtensionInfo,
    apply_viczin_extension_update,
    check_viczin_extension_update,
    disable_viczin_extension,
    enable_viczin_extension,
    get_viczin_extension_bundle_path,
    get_installed_viczin_extension,
    get_installed_viczin_extension_manifest,
    get_installed_viczin_extensions_dir,
    install_viczin_extension,
    list_installed_viczin_extensions,
    load_installed_viczin_extensions,
    uninstall_viczin_extension,
)
from handprint.agent_server.viczin_extensions.manifest import (
    MANIFEST_FILENAME,
    ViczinExtensionContributes,
    ViczinExtensionManifest,
    ViczinExtensionPage,
    resolve_entrypoint,
)


__all__ = [
    "ViczinExtensionManifest",
    "ViczinExtensionContributes",
    "ViczinExtensionPage",
    "MANIFEST_FILENAME",
    "resolve_entrypoint",
    "InstalledViczinExtensionInfo",
    "install_viczin_extension",
    "uninstall_viczin_extension",
    "enable_viczin_extension",
    "disable_viczin_extension",
    "list_installed_viczin_extensions",
    "load_installed_viczin_extensions",
    "get_installed_viczin_extension",
    "get_installed_viczin_extension_manifest",
    "get_installed_viczin_extensions_dir",
    "get_viczin_extension_bundle_path",
    "ViczinExtensionUpdateCheck",
    "check_viczin_extension_update",
    "apply_viczin_extension_update",
]
