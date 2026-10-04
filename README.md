# SailCloth-01 · 帆布浸渍防水台

帆布间布卷与浸渍固化台账基线项目（Django 5 + DRF + Vue 3 SPA）。

## 技术栈

| 层 | 技术 |
| --- | --- |
| 后端 | Django 5 · DRF · SimpleJWT · django-cors-headers · Gunicorn |
| 前端 | Vue 3 · Vite · Pinia · Vue Router |
| 数据库 | PostgreSQL 15 |
| 部署 | Docker Compose · Nginx（前端反代 `/api`） |

## 路径与端口

- **项目路径**：`d:\work\document\bytecode\claudeCodePro\SailCloth\SailCloth-01`
- **前端**：http://localhost:3740
- **API**：http://localhost:8740
- **PostgreSQL**：localhost:6140

## 演示账号

| 用户名 | 密码 | 角色 |
| --- | --- | --- |
| `admin` | `123456` | 管理员 |
| `worker` | `123456` | 操作工 |

登录页已预填 `admin` / `123456`。后端 entrypoint 执行 migrate + seed。

## 业务规则

布卷状态不可设为「已固化」（`cured`），除非该卷**最近一条** `DipRun` 的 `cureHours` 已记录且 **≥ 12**。

**湿度计止日贴纸**：每间帆布间现行（未作废）贴纸最多一张，字段为帆布间 / 仪器编号 / 止日 / 粘贴人 / 作废时刻（可空），止日不得为空。止日当天仍有效；过了止日（或无贴纸）禁止给浸渍补写或改写固化时长，服务端以中文拒绝。登记新浸渍且时长留空不看贴纸。贴纸不替代「标已固化需满 12 小时」。仅管理员可粘贴、续期、作废；操作工可写时长但改不了止日。同一间的粘贴 / 续期 / 作废在该间行锁内串行，续期为原位更新——并发交叉改止日库里只留一版，且数据库部分唯一约束保证不会出现两张现行贴纸并存。

规则实现：`backend/core/rules.py`（时长规则与贴纸闸）、`backend/core/views.py`（贴纸接口与锁）

## 快速启动

```bash
cd d:\work\document\bytecode\claudeCodePro\SailCloth\SailCloth-01
docker compose up --build
```

浏览器打开 http://localhost:3740

## SPA 信息架构

- **登录** → 进入主工作面
- **`/` 帆布间晾晒架（主）**：按帆布间挂布卷芯片（挂签状态 `raw` / `dipping` / `cured`）；点击打开右侧面板登记 `DipRun`、补写/改写固化时长、切换固化状态；面板顶部显示本间贴纸状态；架下为浸渍流水次要信息流
- **`/stickers` 止日贴纸（主）**：各间现行贴纸一览，管理员可粘贴、续期、作废，并查看已作废历史
- **`/rolls` · `/dips`（次要台账）**：保留列表/表单 CRUD，侧栏降级为「台账」入口，非主路径

API 契约不变（JWT、`/api/lofts|rolls|dips|dashboard/`），新增 `/api/stickers/`（含 `renew` / `void` 动作），`/api/dips/` 开放 `PATCH` 用于补写/改写固化时长。

## 配色

海军蓝（navy）+ 帆布米色（canvas），与温室绿主题区分。
