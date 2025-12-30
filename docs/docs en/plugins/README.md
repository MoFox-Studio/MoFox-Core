# 📚 MoFox-Bot Plugin Development Documentation Navigation

Welcome to the MoFox-Bot plugin system development documentation! This document helps you quickly find the learning resources you need.

---

## 🎯 Where Should I Start?

### First Time Developing Plugins?
👉 **Start Here**: [Quick Start Guide](quick-start.md)

This is a step-by-step tutorial that takes you from scratch to creating your first plugin, complete with code examples.

### Encountered an Issue?
👉 **Check Here First**: [Troubleshooting Guide](troubleshooting-guide.md) ⭐

Contains solutions for the 10 most common problems, may solve your problem in just 5 minutes.

### Want to Deep Dive into Specific Features?
👉 **Check the Classification Navigation Below** to find the documentation you need.

---

## 📖 Learning Path Recommendations

### 🌟 Beginner Path (Read in Order)

1. **[Quick Start Guide](quick-start.md)** ⭐ Must Read
   - Create plugin directory and configuration
   - Implement your first Action component
   - Implement your first Command component
   - Add configuration file
   - Estimated reading time: 30-45 minutes

2. **[Enhanced Command Guide](PLUS_COMMAND_GUIDE.md)** ⭐ Must Read
   - Understand the difference between PlusCommand and BaseCommand
   - Learn command parameter handling
   - Master return value specifications
   - Estimated reading time: 20-30 minutes

3. **[Action Component Details](action-components.md)** ⭐ Must Read
   - Understand Action activation mechanisms
   - Learn custom activation logic
   - Master Action use cases
   - Estimated reading time: 25-35 minutes

4. **[Troubleshooting Guide](troubleshooting-guide.md)** ⭐ Recommended Bookmark
   - Common errors and solutions
   - Best practices quick reference
   - Debugging tips
   - Keep on hand for quick reference

---

### 🚀 Advanced Path (Select Based on Needs)

#### Need a Configuration System?
- **[Configuration File System Guide](configuration-guide.md)**
  - Auto-generate configuration files
  - Configuration Schema definition
  - Configuration reading and validation

#### Need to Respond to Events?
- **[Event System Guide](event-system-guide.md)**
  - Subscribe to system events
  - Create custom events
  - Event handler implementation

#### Need to Integrate External Functions?
- **[Tool Component Guide](tool_guide.md)**
  - Provide tool calling capability to LLM
  - Function call integration
  - Tool parameter definition

#### Need to Depend on Other Plugins?
- **[Dependency Management Guide](dependency-management.md)**
  - Declare plugin dependencies
  - Python package dependencies
  - Dependency version management

#### Need Advanced Activation Control?
- **[Action Activation Mechanism Refactoring Guide](action-activation-guide.md)**
  - Custom activation logic
  - Keyword matching activation
  - LLM intelligent judging activation
  - Random activation strategies

---

## 📂 Documentation Structure Explanation

### Core Documentation (Must Read)

```
📄 quick-start.md              Quick Start Guide ⭐ Must Read for Beginners
📄 PLUS_COMMAND_GUIDE.md       Enhanced Command System Guide ⭐ Must Read
📄 action-components.md        Action Component Details ⭐ Must Read
📄 troubleshooting-guide.md    Troubleshooting Guide ⭐ Check This First When Issues Arise
```

### Advanced Documentation (Read as Needed)

```
📄 configuration-guide.md      Configuration System Details
📄 event-system-guide.md       Event System Details
📄 tool_guide.md               Tool Component Details
📄 action-activation-guide.md  Action Activation Mechanism Details
📄 dependency-management.md    Dependency Management Details
📄 manifest-guide.md           Manifest File Specification
```

### API Reference Documentation

```
📁 api/                        API Reference Directory
  ├── Message Related
  │   ├── send-api.md          Message Sending API
  │   ├── message-api.md       Message Processing API
  │   └── chat-api.md          Chat Stream API
  │
  ├── AI Related
  │   ├── llm-api.md           LLM Interaction API
  │   └── generator-api.md     Reply Generation API
  │
  ├── Data Related
  │   ├── database-api.md      Database Operation API
  │   ├── config-api.md        Configuration Reading API
  │   └── person-api.md        Person Relationship API
  │
  ├── Component Related
  │   ├── plugin-manage-api.md 	Plugin Management API
  │   └── component-manage-api.md Component Management API
  │
  └── Other
      ├── emoji-api.md         Emoji API
      ├── tool-api.md          Tool API
      └── logging-api.md       Logging API
```

### Other Files

```
📄 index.md                    Documentation Index (Old Version, Recommend Using This README)
```

---

## 🎓 Find Documentation by Function

### I Want to Create...

| Goal | Recommended Documentation | Difficulty |
|------|----------|------|
| **A Simple Command** | [Quick Start](quick-start.md) → [Enhanced Command Guide](PLUS_COMMAND_GUIDE.md) | ⭐ Beginner |
| **A Smart Action** | [Quick Start](quick-start.md) → [Action Component](action-components.md) | ⭐⭐ Intermediate |
| **A Command with Complex Parameters** | [Enhanced Command Guide](PLUS_COMMAND_GUIDE.md) | ⭐⭐ Intermediate |
| **A Plugin with Configuration** | [Configuration System Guide](configuration-guide.md) | ⭐⭐ Intermediate |
| **A Plugin Responding to System Events** | [Event System Guide](event-system-guide.md) | ⭐⭐⭐ Advanced |
| **Provide Tools to LLM** | [Tool Component Guide](tool_guide.md) | ⭐⭐⭐ Advanced |
| **A Plugin Depending on Other Plugins** | [Dependency Management Guide](dependency-management.md) | ⭐⭐ Intermediate |

### I Want to Learn...

| Topic | Related Documentation |
|------|----------|
| **How to Send Messages** | [Send API](api/send-api.md) / [Enhanced Command Guide](PLUS_COMMAND_GUIDE.md) |
| **How to Handle Parameters** | [Enhanced Command Guide](PLUS_COMMAND_GUIDE.md) |
| **How to Use LLM** | [LLM API](api/llm-api.md) |
| **How to Operate Database** | [Database API](api/database-api.md) |
| **How to Read Configuration** | [Config API](api/config-api.md) / [Configuration System Guide](configuration-guide.md) |
| **How to Get Message History** | [Message API](api/message-api.md) / [Chat Stream API](api/chat-api.md) |
| **How to Send Emojis** | [Emoji API](api/emoji-api.md) |
| **How to Log** | [Logging API](api/logging-api.md) |

---

## 🆘 Encountered an Issue?

### Step 1: Check the Troubleshooting Guide
👉 [Troubleshooting Guide](troubleshooting-guide.md) contains solutions for the 10 most common problems

### Step 2: Check Related Documentation
- **Plugin Can't Load?** → [Quick Start Guide](quick-start.md)
- **Command Not Responding?** → [Enhanced Command Guide](PLUS_COMMAND_GUIDE.md)
- **Action Not Triggering?** → [Action Component Details](action-components.md)
- **Configuration Not Taking Effect?** → [Configuration System Guide](configuration-guide.md)

### Step 3: Check Logs
See `logs/app_*.jsonl` for detailed error information

### Step 4: Seek Help
- Online Documentation: https://mofox-studio.github.io/MoFox-Bot-Docs/
- GitHub Issues: Submit a detailed problem report
- Community Discussion: Join the developer community

---

## 📌 Important Tips

### ⚠️ Common Pitfalls

1. **Don't Use `BaseCommand`**
   - ✅ Use: `PlusCommand`
   - ❌ Avoid: `BaseCommand` (for framework internal use only)

2. **Don't Return User Messages in Return Value**
   - ✅ Use: `await self.send_text("message")`
   - ❌ Avoid: `return True, "message", True`

3. **Must Specify component_type When Manually Creating ComponentInfo**
   - ✅ Recommended: Use `get_action_info()` to auto-generate
   - ⚠️ When Creating Manually: Must specify `component_type=ComponentType.ACTION`

### 💡 Best Practices

- ✅ Always use type annotations
- ✅ Add docstrings for `execute()` methods
- ✅ Use `self.get_config()` to read configuration
- ✅ Use async operations `async/await`
- ✅ Validate parameters before sending messages
- ✅ Provide clear error prompts

---

## 🔄 Documentation Update Log

### v1.1.0 (2024-12-17)
- ✨ Added [Troubleshooting Guide](troubleshooting-guide.md)
- ✅ Fixed BaseCommand examples in [Quick Start Guide](quick-start.md)
- ✅ Enhanced return value explanation in [Enhanced Command Guide](PLUS_COMMAND_GUIDE.md)
- ✅ Improved component_type explanation in [Action Component](action-components.md)
- 📝 Created this navigation document

### v1.0.0 (2024-11)
- 📚 Initial documentation release

---

## 📞 Feedback and Contribution

If you find errors in the documentation or have improvement suggestions:

1. **Submit an Issue**: Submit documentation issues in the GitHub repository
2. **Submit a PR**: Directly modify the documentation and submit a Pull Request
3. **Community Feedback**: Propose suggestions in community discussions

Your feedback is critical to our documentation improvement! 🙏

---

## 🎉 Begin Your Plugin Development Journey

Ready? Start here:

1. 📖 Read [Quick Start Guide](quick-start.md)
2. 💻 Create your first plugin
3. 🔧 Check [Troubleshooting Guide](troubleshooting-guide.md) if you encounter issues
4. 🚀 Explore more advanced features

**Happy coding!** 🎊

---

**Last Updated**: 2024-12-17  
**Documentation Version**: v1.1.0

---

##  Translation Information

This documentation has been translated to English by:

<div align='center'>
<a href='https://github.com/LuisKlee'>
<img src='https://github.com/LuisKlee.png' width='60' height='60' style='border-radius: 50%;' alt='Translator Avatar' />
</a>
<p><strong><a href='https://github.com/LuisKlee'>LuisKlee</a></strong></p>
</div>

###  Disclaimer

Please note that this is a machine-assisted translation. While we strive for accuracy, there may be translation errors or inaccuracies. If you find any issues or have suggestions for improvement, please:

-  Submit an issue on [GitHub](https://github.com/LuisKlee/MoFox-Core)
-  Contribute corrections through pull requests
-  Help us improve the documentation quality

For the most authoritative information, please refer to the [original Chinese documentation](../plugins/).

