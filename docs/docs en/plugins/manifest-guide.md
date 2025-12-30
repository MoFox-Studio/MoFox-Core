# 📄 Plugin Manifest System Guide

## Overview

The MoFox_Bot plugin system now requires every plugin to include a `_manifest.json` file. This file describes the plugin's basic information, dependencies, components and other important metadata.

### 🔄 Configuration Architecture: Manifest and Config Responsibility Separation

To avoid information duplication and improve maintainability, we adopt a **dual-file architecture**:

- **`_manifest.json`** - Plugin's **static metadata**
  - Plugin identity information (name, version, description)
  - Developer information (author, license, repository)
  - System information (compatibility, component list, categories)
  
- **`config.toml`** - Plugin's **runtime configuration**
  - Enable status (`enabled`)
  - Function parameter configuration
  - User-adjustable behavior settings

This separation ensures:
- ✅ Metadata information unified management
- ✅ Runtime configuration flexible adjustment  
- ✅ Avoid duplicate maintenance
- ✅ Clearer responsibility division

## 🔧 Manifest File Structure

### Required Fields

The following fields are required and cannot be empty:

```json
{
  "manifest_version": 1,
  "name": "Plugin Display Name",
  "version": "1.0.0",
  "description": "Plugin Function Description",
  "author": {
    "name": "Author Name"
  }
}
```

### Optional Fields

The following fields are optional and can be added as needed:

```json
{
  "license": "MIT",
  "host_application": {
    "min_version": "1.0.0",
    "max_version": "4.0.0"
  },
  "homepage_url": "https://github.com/your-repo",
  "repository_url": "https://github.com/your-repo",
  "keywords": ["keyword1", "keyword2"],
  "categories": ["category1", "category2"],
  "default_locale": "zh-CN",
  "locales_path": "_locales",
  "plugin_info": {
    "is_built_in": false,
    "plugin_type": "general",
    "components": [
      {
        "type": "action",
        "name": "Component Name",
        "description": "Component Description"
      }
    ]
  }
}
```

## 🛠️ Management Tools

### Using manifest_tool.py

We provide a command-line tool to help manage manifest files:

```bash
# Scan plugins missing manifest
python scripts/manifest_tool.py scan src/plugins

# Create minimal manifest file for plugin
python scripts/manifest_tool.py create-minimal src/plugins/my_plugin --name "My Plugin" --author "Author"

# Create complete manifest template
python scripts/manifest_tool.py create-complete src/plugins/my_plugin --name "My Plugin"

# Validate manifest file
python scripts/manifest_tool.py validate src/plugins/my_plugin
```

### Validation Examples

Successful validation example:
```
✅ Manifest file validation passed
```

Failed validation example:
```
❌ Validation errors:
  - Missing required field: name
  - Author information missing name field or is empty
⚠️ Validation warnings:
  - Recommended field: license
  - Recommended field: keywords
```

## 🔄 Migration Guide

### For Existing Plugins

1. **Check plugins missing manifest**:
   ```bash
   python scripts/manifest_tool.py scan src/plugins
   ```

2. **Create manifest for each plugin**:
   ```bash
   python scripts/manifest_tool.py create-minimal src/plugins/your_plugin
   ```

3. **Edit manifest file** to fill in correct information.

4. **Validate manifest**:
   ```bash
   python scripts/manifest_tool.py validate src/plugins/your_plugin
   ```

### For New Plugins

When creating new plugins, suggested steps:

1. **Create plugin directory and basic files**
2. **Create complete manifest template**:
   ```bash
   python scripts/manifest_tool.py create-complete src/plugins/new_plugin
   ```
3. **Modify manifest file** according to actual situation
4. **Write plugin code**
5. **Validate manifest file**

## 📋 Field Explanation

### Basic Information
- `manifest_version`: Manifest format version, currently 1
- `name`: Plugin display name (required)
- `version`: Plugin version number (required)
- `description`: Plugin function description (required)
- `author`: Author information (required)
  - `name`: Author name (required)
  - `url`: Author homepage (optional)

### License and URLs
- `license`: Plugin license (optional, recommended)
- `homepage_url`: Plugin homepage (optional)
- `repository_url`: Source code repository address (optional)

### Categories and Tags
- `keywords`: Keyword array (optional, recommended)
- `categories`: Category array (optional, recommended)

### Compatibility
- `host_application`: Host application compatibility (optional, recommended)
  - `min_version`: Minimum compatible version
  - `max_version`: Maximum compatible version

⚠️ If not filled, the plugin will default support all versions. **(Due to the extensive refactoring of the plugin system across versions, this situation is almost impossible.)**

### Internationalization
- `default_locale`: Default language (optional)
- `locales_path`: Language file directory (optional)

### Plugin Specific Information
- `plugin_info`: Plugin detailed information (optional)
  - `is_built_in`: Whether it's a built-in plugin
  - `plugin_type`: Plugin type
  - `components`: Component list

## ⚠️ Important Notes

1. **Mandatory Requirement**: All plugins must include `_manifest.json` file, otherwise they cannot be loaded
2. **Encoding Format**: Manifest file must use UTF-8 encoding
3. **JSON Format**: File must be valid JSON format
4. **Required Fields**: `manifest_version`, `name`, `version`, `description`, `author.name` are required
5. **Version Compatibility**: Currently only supports `manifest_version = 1`

## 🔍 Frequently Asked Questions

### Q: Can I skip filling optional fields?
A: Yes. All fields marked as "optional" can be left out, but it's recommended to at least fill in `license` and `keywords`.

### Q: What if manifest validation fails?
A: Fix the issues according to the validator's error message. Errors will prevent plugin loading, warnings will not.

## 📚 Reference Examples

Check the manifest files of built-in plugins as reference:
- `src/plugins/built_in/core_actions/_manifest.json`
- `src/plugins/built_in/tts_plugin/_manifest.json`
- `plugins/hello_world_plugin/_manifest.json`
