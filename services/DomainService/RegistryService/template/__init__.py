"""模板包的公共入口，导出 Registry 文件模板字典，供安装逻辑读取和填充。

Export the Registry template dictionary for the installation helpers.
"""
from .RegistryFileTemplates import RegistryFileTemplates

__all__ = ["RegistryFileTemplates"]
