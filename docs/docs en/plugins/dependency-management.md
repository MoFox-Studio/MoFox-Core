# Python Dependency Management System (Summarized)

For full details, see `docs/plugins/dependency-management.md`.

## Define Dependencies

### Simple Method
```python
python_dependencies = [
    "requests>=2.25.0",
    "beautifulsoup4>=4.9.0"
]
```

### Detailed Method (Recommended)
```python
from src.plugin_system import PythonDependency

python_dependencies = [
    PythonDependency(
        package_name="requests",
        version=">=2.25.0",
        description="HTTP requests library",
        optional=False
    ),
    PythonDependency(
        package_name="bs4",  # Import name
        install_name="beautifulsoup4",  # Package name
        description="HTML parsing library",
        optional=False
    )
]
```

## Configuration

Create `config/dependency_config.toml`:

```toml
[dependency_management]
auto_install = true
auto_install_timeout = 300
use_mirror = true
mirror_url = "https://pypi.tuna.tsinghua.edu.cn/simple"
```

## Mirror Sources

- **Tsinghua**: https://pypi.tuna.tsinghua.edu.cn/simple (Recommended in China)
- **Aliyun**: https://mirrors.aliyun.com/pypi/simple
- **USTC**: https://pypi.mirrors.ustc.edu.cn/simple
- **Douban**: https://pypi.douban.com/simple

## Smart Alias Resolution

System automatically maps package names with different install/import names:

```python
# These work automatically
python_dependencies = ["beautifulsoup4"]  # Auto-resolves to import `bs4`
python_dependencies = ["Pillow"]  # Auto-resolves to import `PIL`
python_dependencies = ["scikit-learn"]  # Auto-resolves to import `sklearn`
```

## Best Practices

✅ Specify version requirements
✅ Use detailed `PythonDependency` for clarity
✅ Set `optional=True` for non-core features
✅ Configure PyPI mirror for speed
✅ Test dependencies in different environments
❌ Don't install packages manually
❌ Don't mix install/import names
