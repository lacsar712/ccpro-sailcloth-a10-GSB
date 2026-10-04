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

规则实现：`backend/core/rules.py`

### 湿度计止日贴纸

每间帆布间一张湿度计止日贴纸（`HygrometerSticker`：帆布间、仪器编号、止日、粘贴人、作废时刻可空）：

- 同一间现行未作废贴纸最多一张（数据库部分唯一约束兜底并发）。
- 止日当天仍有效；过了止日禁止给浸渍**补写或改写**固化时长。没有现行贴纸同样禁止。
- 登记新浸渍且时长留空时不看贴纸。
- 标「已固化」仍要时长满十二小时，贴纸不替代时长。
- 仅管理员可粘贴、续期与作废；操作工可写时长但改不了止日。
- 保存固化时长在**后端**校验该间现行贴纸（`rules.cure_hours_gate`），右侧面板不只藏按钮。

页面：顶栏「止日贴纸」专页（现行贴纸、粘贴、续期、作废）；晾晒架右侧面板与本卷浸渍列表可补写/改写时长。

API：`GET/POST /api/stickers/`、`PATCH /api/stickers/{id}/`（续期）、`POST /api/stickers/{id}/void/`、`PATCH /api/dips/{id}/`（补写/改写时长）。

种子：北岸帆布间浸渍中卷 R-01 时长仍空，贴纸止日写成昨天（已过期，写时长会被中文挡住）。

## 快速启动

```bash
cd d:\work\document\bytecode\claudeCodePro\SailCloth\SailCloth-01
docker compose up --build
```

浏览器打开 http://localhost:3740

## SPA 信息架构

- **登录** → 进入主工作面
- **`/` 帆布间晾晒架（主）**：按帆布间挂布卷芯片（挂签状态 `raw` / `dipping` / `cured`）；点击打开右侧面板登记 `DipRun`、补写/改写固化时长、切换固化状态；架下为浸渍流水次要信息流
- **`/stickers` 止日贴纸**：各帆布间现行贴纸一览；管理员粘贴、续期、作废
- **`/rolls` · `/dips`（次要台账）**：保留列表/表单 CRUD，顶栏降级为「台账」入口，非主路径

完整顶栏直达晾晒架与止日贴纸。API 契约：JWT，`/api/lofts|rolls|dips|stickers|dashboard/`。

## 配色

海军蓝（navy）+ 帆布米色（canvas），与温室绿主题区分。
