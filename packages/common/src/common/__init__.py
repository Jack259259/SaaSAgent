"""共享底座包(common)。

提供跨服务复用的最小原语骨架(阶段 0 仅空壳,具体实现见后续阶段):

- :mod:`common.auth_ctx`:零信任身份上下文 user_ctx(红线 3)。
- :mod:`common.audit`:结构化审计事件(红线 4 / §9.2)。
- :mod:`common.errors`:统一错误枚举,映射到 ToolSpec.errors(§6 错误处理)。
"""

__version__ = "0.1.0"
