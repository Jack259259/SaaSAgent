# run_analysis 沙箱:实现与生产化(红线 11)

`run_analysis` 让模型生成的分析代码在受限沙箱内执行(透视/统计/绘图),产物只回工作区句柄。
**红线 11**:无网络、无库连接、只读挂载传入句柄、CPU/内存/时长限额、产物只回句柄、沙箱内不调任何其他工具。

## 两个运行器(SandboxRunner 接口)

### SubprocessRunner(开发 / CI;本仓默认)

独立子进程 + 注入式护栏(`sandbox_svc/_harness.py`),**best-effort**:

| 隔离项 | 手段 | 平台 |
|--------|------|------|
| 无网络 | `socket.socket`/`create_connection`/`create_server` 注入抛错;env 不含代理 | 跨平台 |
| 路径隔离 | `builtins.open` 守卫:读限 sandbox + python 前缀,写限 sandbox | 跨平台 |
| 时长限额 | 父进程 `subprocess.run(timeout=)` 超时 kill | 跨平台 |
| CPU 限额 | 子进程 `resource.setrlimit(RLIMIT_CPU)` | 仅 POSIX |
| 内存限额 | 子进程 `setrlimit(RLIMIT_AS)`(预热重库后,当前虚拟内存 + headroom) | 仅 POSIX(Linux) |
| import 白名单 | `sys.meta_path` 守卫:标准库 + pandas/numpy/matplotlib,剔除逃逸 stdlib(subprocess 等) | 跨平台 |
| 无库连接 | env keeplist **不含** `DB_DSN_READONLY`/`LLM_API_KEY`/代理;叠加无网络 | 跨平台 |

**已知局限(故需 ContainerRunner)**:注入式护栏可被绕过——`subprocess`/C 层文件 IO 可逃逸 `open` 守卫;
Windows 无 `resource`(CPU/内存限额仅 POSIX,本机由墙钟超时兜底)。**绝不能用 SubprocessRunner 跑不可信代码于生产。**

### ContainerRunner(生产;本阶段仅接口 + TODO)

生产环境对不可信代码必须用真正的内核级隔离。生产化要求:

- **容器 / gVisor(runsc)**:syscall 拦截,强隔离;只读 rootfs;非 root 运行;`--cap-drop=ALL`;seccomp 限制 syscall。
- **网络命名空间**:`unshare -n` / 容器 `--network=none`,彻底断网(不靠 socket 注入)。
- **文件挂载**:输入句柄以**只读** bind mount 挂入;仅产物目录可写;无主机敏感路径。
- **资源限额**:cgroups 限 CPU/内存/PID/磁盘;墙钟超时杀容器。
- **凭据**:容器内**无任何** DB 连接串、API Key、云元数据访问(屏蔽 169.254.169.254)。
- **依赖白名单**:镜像仅装 pandas/numpy/matplotlib + 标准库;无包管理器。

接口契约(两个 Runner 共用):`SandboxRunner.run(SandboxRequest) -> SandboxResult`(见 `sandbox_svc/runner.py`)。
切换生产只需把 orchestrator 注册 `run_analysis` 时注入的 runner 从 `SubprocessRunner()` 换为 `ContainerRunner(...)`。

## 沙箱内代码约定(注入到执行全局)

- `INPUTS`:只读输入文件的相对路径列表(对应传入的 input_handles,如 `inputs/input_0.csv`)。
- `OUTPUT_DIR`:产物目录(`"artifacts"`);写入此目录的文件会被回收为新的工作区句柄。
- stdout 截断后回传;沙箱内**无**工具注册表/编排器/网络,无法调用任何其他工具。
