# 北京国安 2026 赛季数据仪表盘

北京国安足球俱乐部 2026 赛季专属数据追踪仪表盘。支持微信小程序 web-view 嵌入。

## 核心功能

- **7 视图**：概览、赛程与事件、球员表现、对手分析、历史对战、状态与情境、球队资料
- **多维度数据**：30 场比赛、进球时间分布、排名走势、球员深度统计、三年 H2H 记录
- **自动更新**：每日凌晨 2:30 自动构建部署

## 快速开始

```bash
# 1. 构建数据
python -m src.guoan_builder

# 2. 本地预览
cd web && python -m http.server 8080
```

## 数据来源

- 2026 赛季：CSL Dashboard (`dashboard_embed.json`)
- 历史对战：2024/2025 赛季比赛数据
- 球员档案：中足联 CFL 注册信息

## 部署

- **GitHub Pages**：推送 `main` 分支自动部署
- **微信小程序**：作为 web-view 源 URL，无需额外适配

## 技术栈

- Python stdlib（零外部依赖）
- Vanilla JavaScript（零框架）
- 轻量暗色主题 CSS（~12KB，零 CDN）
