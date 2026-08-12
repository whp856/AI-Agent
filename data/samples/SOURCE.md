# 样例数据来源说明

## 数据来源（真实数据，非伪造）

`data/cache/839285684.json` 包含 **50 条真实用户评论**，来自 Apple 官方 iTunes RSS 评论接口：

```
https://itunes.apple.com/rss/customerreviews/page=1/id=839285684/sortBy=mostRecent/json
```

应用：Workout for Women - Home Gym（App Store id=839285684）
国家/地区：美国区（US）
数据时间范围：约 2026-07（评论 `updated` 字段可查）
原始响应存档：`data/samples/raw_rss_page1.json`（iTunes 官方接口原始 JSON 输出，逐条转换，
未修改任何评论文本、评分、作者）

## 获取途径说明

- 本项目正常运行时由 `scripts/fetch_cache.py`（backend/tools/collector.py）实时请求上述
  官方接口并缓存；
- 本仓库开发环境无法直连 Apple 域名，为提供可复现演示数据，将公开渠道可获取的该接口
  原始响应（SHA 68af1672daf6183aa1fd3e64f89c20641bf17b03）导入为缓存；
- 缓存仅作演示与评审兜底，系统仍具备实时采集全新链接的能力。

## 局限性（如实声明）

1. 每请求最多 50 条、仅最近评论，无全量历史；
2. 单页窗口数据，分析结论受时间窗口限制；
3. 评论删除后不可回溯。
