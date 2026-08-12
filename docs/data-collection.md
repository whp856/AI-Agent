# 数据采集方案说明

## 方案选型：iTunes 官方 RSS 评论接口

**最终方案**：Apple 官方公开的 iTunes RSS 评论 Feed 接口，无需登录、无需 token、稳定合规。

```
GET https://itunes.apple.com/rss/customerreviews/id={appId}/sortBy=mostRecent/json
GET https://itunes.apple.com/rss/customerreviews/page={page}/id={appId}/sortBy=mostRecent/json
```

实现：`backend/tools/collector.py`（约 150 行自研封装，无第三方依赖）。

## 候选方案对比（为什么不用其它方案）

| 候选方案 | 问题 |
|---|---|
| 爬取 App Store 网页版详情页 | 页面为 JS 动态渲染 + 反爬签名；任务提示明确不建议抓页面可见内容；违反"禁止对目标站点造成异常访问压力" |
| 爬取 iTunes 网页版评论列表 | 非官方接口，结构随更新变化，易碎 |
| **iTunes RSS 官方接口（选用）** | **Apple 官方公开 API，专供开发者消费；纯 JSON；无需认证；频率限制友好；多年稳定** |
| 第三方聚合库（如 app-store-scraper） | 依赖社区维护，质量参差；自研薄封装使数据源与局限完全可控 |

## 字段映射

RSS `feed.entry[]` 各条评论字段 → 系统 `Review` 模型：

| RSS 字段 | 模型字段 | 说明 |
|---|---|---|
| id.label | review_id | 评论 ID（去 `?` 查询串） |
| title.label | title | 标题 |
| content.label | body | 正文 |
| im:rating.label | rating | 评分 1-5 |
| author.name.label | author | 作者 |
| im:version.label | version | 应用版本 |
| updated.label | updated | 评论时间 |
| — | country=US | 数据源固定美国区（任务要求） |

## 合规与频率控制

- 单应用采集限速 **≥2 秒/请求**（`COLLECT_RATE_LIMIT_SECONDS`）；
- 最多 **5 页**（约 250 条）上限（`COLLECT_MAX_PAGES`），可配置；
- 失败指数退避重试（1s/2s/4s，最多 3 次），单页失败即停止分页；
- 采集结果**本地缓存** `data/cache/{appId}.json`：演示与面试重复分析不产生请求压力；
- 串行采集，无并发，杜绝压测式访问。

## 数据源局限（如实声明）

1. 每次请求最多返回 **50 条**评论；
2. 仅能获取**最近**评论（无全量历史、无评论总数）；
3. 评论删除后不可回溯；
4. 多语言评论均可能返回，语言标签由系统清洗阶段检测；
5. 分析结论均基于采集窗口数据，快照 `collect_note` 与 UI「数据与局限」Tab 如实标注。

## 样例数据（data/cache/839285684.json）

- 50 条**真实用户评论**（Workout for Women - Home Gym，id=839285684，约 2026-07 窗口）；
- 原始 RSS 响应存档于 `data/samples/raw_rss_page1.json`，逐条转换未修改任何内容；
- 来源与获取途径详见 `data/samples/SOURCE.md`；
- **定位**：仅作演示与评审兜底，不替代系统读取全新链接、全新数据集的能力（网络与模型配置就绪时实时采集）。

## 导入能力（JSON/CSV）

- `POST /api/analyze-import`：上传评论文件直接启动完整工作流；
- 兼容字段：`review_id / title / body / rating / author / version / updated`；
- 缺少 `review_id` 自动生成稳定哈希 ID（`generated:{hash}`）并如实标注来源 `import`；
- 导入数据走与采集数据完全相同的 S2-S7 全流程。
