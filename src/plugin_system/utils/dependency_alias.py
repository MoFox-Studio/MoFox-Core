"""
本模块包含一个从Python包的“安装名”到其“导入名”的映射。

这个映射表主要用于解决一个常见问题：某些Python包通过pip安装时使用的名称
与在代码中`import`时使用的名称不一致。例如，我们使用`pip install beautifulsoup4`
来安装，但在代码中却需要`import bs4`。

当插件系统检查依赖时，如果一个开发者只简单地在依赖列表中写了安装名
（例如 "beautifulsoup4"），标准的导入检查`import('beautifulsoup4')`会失败。
通过这个映射表，依赖管理器可以在初次导入检查失败后，查询是否存在一个
已知的别名（例如 "bs4"），并尝试使用该别名进行二次导入检查。

这样做的好处是：
1. 提升开发者体验：插件开发者无需强制记忆这些特殊的名称对应关系，或者强制
   使用更复杂的`PythonDependency`对象来分别指定安装名和导入名。
2. 增强系统健壮性：减少因名称不一致导致的插件加载失败问题。
3. 兼容性：对遵循最佳实践、正确指定了`package_name`和`install_name`的
   开发者没有任何影响。

开发者可以持续向这个列表中贡献新的映射关系，使其更加完善。
"""

INSTALL_NAME_TO_IMPORT_NAME = {
    # ============== 数据科学与机器学习 (Data Science & Machine Learning) ==============
    "scikit-learn": "sklearn",  # 机器学习库
    "scikit-image": "skimage",  # 图像处理库
    "opencv-python": "cv2",  # OpenCV 计算机视觉库
    "opencv-contrib-python": "cv2",  # OpenCV 扩展模块
    "tensorflow-gpu": "tensorflow",  # TensorFlow GPU版本
    "tensorboardx": "tensorboardX",  # TensorBoard 的封装
    "torchvision": "torchvision",  # PyTorch 视觉库 (通常与 torch 一起)
    "torchaudio": "torchaudio",  # PyTorch 音频库
    "catboost": "catboost",  # CatBoost 梯度提升库
    "lightgbm": "lightgbm",  # LightGBM 梯度提升库
    "xgboost": "xgboost",  # XGBoost 梯度提升库
    "imbalanced-learn": "imblearn",  # 处理不平衡数据集
    "seqeval": "seqeval",  # 序列标注评估
    "gensim": "gensim",  # 主题建模和NLP
    "nltk": "nltk",  # 自然语言工具包
    "spacy": "spacy",  # 工业级自然语言处理
    "fuzzywuzzy": "fuzzywuzzy",  # 模糊字符串匹配
    "python-levenshtein": "Levenshtein",  # Levenshtein 距离计算
    # ============== Web开发与API (Web Development & API) ==============
    "python-socketio": "socketio",  # Socket.IO 服务器和客户端
    "python-engineio": "engineio",  # Engine.IO 底层库
    "aiohttp": "aiohttp",  # 异步HTTP客户端/服务器
    "python-multipart": "multipart",  # 解析 multipart/form-data
    "uvloop": "uvloop",  # 高性能asyncio事件循环
    "httptools": "httptools",  # 高性能HTTP解析器
    "websockets": "websockets",  # WebSocket实现
    "fastapi": "fastapi",  # 高性能Web框架
    "starlette": "starlette",  # ASGI框架
    "uvicorn": "uvicorn",  # ASGI服务器
    "gunicorn": "gunicorn",  # WSGI服务器
    "django-rest-framework": "rest_framework",  # Django REST框架
    "django-cors-headers": "corsheaders",  # Django CORS处理
    "flask-jwt-extended": "flask_jwt_extended",  # Flask JWT扩展
    "flask-sqlalchemy": "flask_sqlalchemy",  # Flask SQLAlchemy扩展
    "flask-migrate": "flask_migrate",  # Flask Alembic迁移扩展
    "python-jose": "jose",  # JOSE (JWT, JWS, JWE) 实现
    "passlib": "passlib",  # 密码哈希库
    "bcrypt": "bcrypt",  # Bcrypt密码哈希
    # ============== 数据库 (Database) ==============
    "psycopg2-binary": "psycopg2",  # PostgreSQL驱动 (二进制)
    "pymongo": "pymongo",  # MongoDB驱动
    "redis": "redis",  # Redis客户端
    "aioredis": "aioredis",  # 异步Redis客户端
    "sqlalchemy": "sqlalchemy",  # SQL工具包和ORM
    "alembic": "alembic",  # SQLAlchemy数据库迁移工具
    "tortoise-orm": "tortoise",  # 异步ORM
    # ============== 图像与多媒体 (Image & Multimedia) ==============
    "Pillow": "PIL",  # Python图像处理库 (PIL Fork)
    "moviepy": "moviepy",  # 视频编辑库
    "pydub": "pydub",  # 音频处理库
    "pycairo": "cairo",  # Cairo 2D图形库的Python绑定
    "wand": "wand",  # ImageMagick的Python绑定
    # ============== 解析与序列化 (Parsing & Serialization) ==============
    "beautifulsoup4": "bs4",  # HTML/XML解析库
    "lxml": "lxml",  # 高性能HTML/XML解析库
    "PyYAML": "yaml",  # YAML解析库
    "python-dotenv": "dotenv",  # .env文件解析
    "python-dateutil": "dateutil",  # 强大的日期时间解析
    "protobuf": "google.protobuf",  # Protocol Buffers
    "msgpack": "msgpack",  # MessagePack序列化
    "orjson": "orjson",  # 高性能JSON库
    "pydantic": "pydantic",  # 数据验证和设置管理
    # ============== 系统与硬件 (System & Hardware) ==============
    "pyserial": "serial",  # 串口通信
    "pyusb": "usb",  # USB访问
    "pybluez": "bluetooth",  # 蓝牙通信 (可能因平台而异)
    "psutil": "psutil",  # 系统信息和进程管理
    "python-gnupg": "gnupg",  # GnuPG的Python接口
    # ============== 加密与安全 (Cryptography & Security) ==============
    "pycrypto": "Crypto",  # 加密库 (较旧)
    "pycryptodome": "Crypto",  # PyCrypto的现代分支
    "cryptography": "cryptography",  # 现代加密库
    "pyopenssl": "OpenSSL",  # OpenSSL的Python接口
    "service-identity": "service_identity",  # 服务身份验证
    # ============== 工具与杂项 (Utilities & Miscellaneous) ==============
    "setuptools": "setuptools",  # 打包工具
    "pip": "pip",  # 包安装器
    "tqdm": "tqdm",  # 进度条
    "regex": "regex",  # 替代的正则表达式引擎
    "colorama": "colorama",  # 跨平台彩色终端文本
    "termcolor": "termcolor",  # 终端颜色格式化
    "requests-oauthlib": "requests_oauthlib",  # OAuth for Requests
    "oauthlib": "oauthlib",  # 通用OAuth库
    "authlib": "authlib",  # OAuth和OpenID Connect客户端/服务器
    "pyjwt": "jwt",  # JSON Web Token实现
    "python-editor": "editor",  # 程序化地调用编辑器
    "prompt-toolkit": "prompt_toolkit",  # 构建交互式命令行
    "pygments": "pygments",  # 语法高亮
    "tabulate": "tabulate",  # 生成漂亮的表格
    "nats-client": "nats",  # NATS客户端
    "gitpython": "git",  # Git的Python接口
    "pygithub": "github",  # GitHub API v3的Python接口
    "python-gitlab": "gitlab",  # GitLab API的Python接口
    "jira": "jira",  # JIRA API的Python接口
    "python-jenkins": "jenkins",  # Jenkins API的Python接口
    "huggingface-hub": "huggingface_hub",  # Hugging Face Hub API
    "apache-airflow": "airflow",  # Airflow工作流管理
    "pandas-stubs": "pandas-stubs",  # Pandas的类型存根
    "data-science-types": "data_science_types",  # 数据科学类型
    # ============== 语音 ==============
    "openai-whisper": "whisper"  # 用于本地语音转文本功能
}
