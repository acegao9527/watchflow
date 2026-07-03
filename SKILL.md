---
name: watchflow
description: "从豆瓣想看列表筛选电影/电视剧，检索有效夸克资源，转存到夸克网盘电影/电视剧下载目录，并统一命名，形成可同步到 NAS 的媒体入库流水线。"
version: 1.0.0
author: Community
license: MIT
metadata:
  hermes:
    tags: [watchflow, douban, wish, quark, movie, show, media-library, rename]
---

# WatchFlow

用于把豆瓣想看列表自动转成夸克网盘下载目录，并进一步衔接 NAS / 家庭媒体库。

## 目标形态

```text
夸克网盘/电影下载/电影名称 (年份)/电影名称 (年份).mkv
夸克网盘/电视剧下载/剧集名称 (年份)/...
```

## 使用方式

默认使用内置 `wp365` 资源搜索 provider，因此最小配置只需要豆瓣 ID 和夸克 Cookie：

```bash
python3 src/watchflow.py \
  --config config.json \
  --count 5 \
  --max-pages 5
```

如果要使用自己的聚合搜索接口：

```bash
python3 src/watchflow.py \
  --config config.json \
  --search-provider custom \
  --search-endpoint http://127.0.0.1:8888/api/search
```

复用缓存分批跑：

```bash
python3 src/watchflow.py \
  --config config.json \
  --use-existing \
  --start-index 100 \
  --count 20
```

## 配置

复制：

```bash
cp examples/config.example.json config.json
```

`config.json` 包含私密信息，不要提交。默认配置文件路径：

```text
~/.config/watchflow/config.json
```

## 安全规则

- 不提交豆瓣 ID、夸克 Cookie、私有搜索接口。
- 默认使用公开 `wp365` provider；私有聚合 API 是可选项。
- 不删除网盘文件。
- 电视剧只规范顶层文件夹，不乱改内部集数文件。
- 电影只有单个主视频时才自动重命名视频文件。
- 资源标题太短或疑似短剧/错剧时宁可跳过，不要误存。
