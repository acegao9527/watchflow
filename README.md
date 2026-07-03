# WatchFlow

Turn your watchlist into a ready-to-watch media library.

WatchFlow 把豆瓣“想看/待看”列表变成一个自动化媒体入库流水线：

1. 抓取豆瓣待看条目；
2. 识别电影 / 电视剧；
3. 默认调用内置 `wp365` 资源站 provider 检索并解密夸克网盘链接；
4. 验证夸克分享链接是否有效；
5. 转存到夸克网盘的 `电影下载` / `电视剧下载`；
6. 统一命名：
   - 电影：`电影名称 (年份)/电影名称 (年份).mkv`
   - 剧集：`剧集名称 (年份)/...`（只规范顶层文件夹，不破坏集数文件名）

这个项目源自一次真实的 Agent 自动化实践：Agent 分批扫描豆瓣待看，找到可用夸克资源，保存到网盘。后续如果你的 NAS / 极空间 / 群晖会同步夸克目录，就可以形成“豆瓣待看 → 夸克 → NAS 媒体库”的自动链路。

![WatchFlow 从豆瓣待看到媒体库的自动化流程](assets/watchflow-pipeline-labeled.png)

_豆瓣想看/待看 → WatchFlow Skill → 资源搜索与链接校验 → 夸克网盘 → 可选 NAS / 媒体库_

## 项目来源

WatchFlow 基于 [DavidBB-L/cinema-manager](https://github.com/DavidBB-L/cinema-manager) 的 Hermes Skill 思路继续扩展。`cinema-manager` 已经提供了“影视资源搜索 → 质量评分 → 夸克网盘保存 → 媒体库整理”的基础流程，并支持通过插件接入不同内容源。

WatchFlow 在这个流程前面增加了一层豆瓣入口：不再需要逐部告诉 Agent “我要看某部电影”，而是把豆瓣“想看”列表当作待处理队列，批量完成抓取、分类、搜索、验证、转存和命名。

过去如果想做“豆瓣想看自动下载”，常见方案是：

```text
豆瓣想看/RSS → PT 站点 → 下载器 → NAS 工具 → 媒体库
```

这通常依赖 PT 账号、站点规则、下载器和 NAS 侧工具链。WatchFlow 把这条链路收敛成一个更轻量的 Skill/CLI：

```text
豆瓣想看 → WatchFlow → 夸克网盘 → 可选 NAS 同步/媒体库刮削
```

也就是说，NAS 仍然可以作为后续同步和播放层，但不再是整个流程的前置条件；PT 也不是必需入口。最小使用形态只需要豆瓣 ID、夸克 Cookie，以及一个可用的资源搜索 provider。

## 特性

- 开箱即用：内置 `wp365` 资源搜索 provider，只需要豆瓣 ID 和夸克 Cookie
- 可分批续跑：`--start-index` + `--use-existing`
- 可审阅再保存：`--review` 会展示候选、评分和校验结果，不转存
- 可恢复运行：默认写入 `~/.config/watchflow/state.jsonl`，可用 `--skip-done` 跳过已完成条目
- 支持电影 / 电视剧分流
- 夸克链接 token API 验证，不用网页 200 假判断
- 电影主视频和字幕安全重命名
- 支持按豆瓣 `subject_id` 手动修正标题、年份、类型或跳过
- 避免常见误命中：短剧、子串标题、剧集误入电影目录
- 不删除任何网盘文件，失败记录后继续

## 安装

```bash
git clone https://github.com/acegao9527/watchflow.git
cd watchflow
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
cp examples/config.example.json config.json
```

编辑 `config.json`，填入你自己的豆瓣 ID 和夸克 Cookie。默认使用内置 `wp365` provider 搜索资源，不需要私有搜索接口。不要提交真实配置。

安装后可以使用两种命令形式：

```bash
watchflow --help
python3 src/watchflow.py --help
```

## 配置

```json
{
  "douban_user_id": "你的豆瓣用户 ID",
  "quark_cookie": "你的夸克 Cookie",
  "search_provider": "wp365",
  "wp365_base_url": "https://pan.365wp.top",
  "search_endpoint": "",
  "movie_folder": "电影下载",
  "show_folder": "电视剧下载",
  "overrides": {
    "豆瓣subject_id": {
      "title": "手动修正标题",
      "year": "2024",
      "media_type": "movie",
      "skip": false
    }
  }
}
```

也可以用环境变量覆盖：

```bash
export DOUBAN_USER_ID="..."
export QUARK_COOKIE="..."
# 可选：改用自定义资源搜索 API
export SEARCH_PROVIDER="custom"
export MEDIA_SEARCH_ENDPOINT="http://127.0.0.1:8888/api/search"
```

默认配置文件路径：

```text
~/.config/watchflow/config.json
```

## 快速试跑

只抓取并打印样例，不搜索、不转存：

```bash
watchflow \
  --config config.json \
  --max-pages 1 \
  --count 5 \
  --dry-run
```

审阅候选资源，不转存：

```bash
watchflow \
  --config config.json \
  --max-pages 1 \
  --count 5 \
  --review
```

第一次正式保存建议只跑 1 条：

```bash
watchflow \
  --config config.json \
  --count 1 \
  --max-pages 1
```

正式保存 5 条：

```bash
watchflow \
  --config config.json \
  --count 5 \
  --max-pages 5
```

复用已有缓存继续跑：

```bash
watchflow \
  --config config.json \
  --use-existing \
  --start-index 100 \
  --skip-done \
  --count 20
```

只处理电影 / 电视剧：

```bash
watchflow --config config.json --media-type movie --count 10
watchflow --config config.json --media-type show --count 10
```

如果夸克根目录下还没有 `电影下载` / `电视剧下载`，先手动创建，或尝试：

```bash
watchflow --config config.json --create-folders --count 1
```

`--create-folders` 依赖底层夸克客户端是否支持创建目录；如果失败，按提示手动创建即可。

## 资源搜索 Provider

默认 provider 是 `wp365`，会调用公开资源站：

```text
https://pan.365wp.top/api/interface/search
https://pan.365wp.top/api/transfer-share/transfer-share
```

这意味着最小配置只需要：

```json
{
  "douban_user_id": "你的豆瓣用户 ID",
  "quark_cookie": "你的夸克 Cookie"
}
```

如果你有自己的聚合搜索接口，可以切换到 `custom`：

```json
{
  "search_provider": "custom",
  "search_endpoint": "http://127.0.0.1:8888/api/search"
}
```

自定义接口约定：

```text
POST /api/search
```

请求体示例：

```json
{
  "kw": "流浪地球",
  "cloud_types": ["quark"],
  "filter": {
    "exclude": ["预告", "花絮", "解说", "枪版", "TC", "TS", "CAM", "抢先"]
  }
}
```

期望返回结构兼容：

```json
{
  "data": {
    "merged_by_type": {
      "quark": [
        {"url": "https://pan.quark.cn/s/xxxx", "note": "资源标题"}
      ]
    }
  }
}
```

也兼容部分二次包裹结构：`data.data.merged_by_type.quark`。

`wp365` 是实验性默认 provider，稳定性、可用性和返回质量取决于第三方服务。WatchFlow 只做接口适配、候选评分、链接校验和转存调用，不托管资源，也不保证第三方资源可用。

## 状态与续跑

默认状态文件：

```text
~/.config/watchflow/state.jsonl
```

每处理一条会追加一行 JSON，包含豆瓣 `subject_id`、标题、动作、原因和候选结果。再次运行时加上 `--skip-done`，会跳过状态文件中已经 `saved` 或 `skip_exists` 的条目。

如果你不想保留分享链接等运行记录，可以删除这个文件；它不是程序继续运行的强依赖。

## 安全与脱敏

- 本项目不提供、不托管任何影视资源，只面向个人媒体库自动化管理场景。请确保你对保存和使用的内容拥有相应权利。
- 仓库不包含豆瓣 ID、夸克 Cookie、私有搜索接口地址。
- `config.json` 已加入 `.gitignore`。
- 不输出 Cookie / token。
- 不删除网盘文件。
- 建议先 `--dry-run`，再 `--review`，最后小批量正式保存。

## Troubleshooting

| 现象 | 可能原因 | 处理方式 |
| --- | --- | --- |
| `missing dependency: httpx` | 未安装依赖 | 运行 `pip install -e .` 或 `pip install -r requirements.txt` |
| 豆瓣抓取 0 条 | 豆瓣列表非公开、需要登录或触发反爬 | 传入 `--douban-cookie` 或先确认列表公开可访问 |
| `Quark root folder not found` | 夸克根目录没有目标文件夹 | 创建 `电影下载` / `电视剧下载`，或尝试 `--create-folders` |
| `no_verified_candidate` | 候选链接无效或标题匹配过于宽泛 | 先跑 `--review` 查看候选，必要时用 `overrides` 修正标题/年份 |
| 夸克转存超时 | 资源较大或夸克任务处理慢 | 增大 `--timeout`，稍后用缓存和 `--skip-done` 续跑 |
| 类型识别错误 | 豆瓣简介信息不足或条目形态特殊 | 在 `overrides` 中按 `subject_id` 指定 `media_type` |

## 局限

- 豆瓣公开页面可能受登录状态、反爬、隐私设置影响。
- 电影 / 剧集分类是启发式规则，长剧集、短纪录片、动画条目需要人工抽查。
- 资源搜索质量取决于 provider。
- 夸克转存后有时会处于“下载中”，重命名可能需要稍后重试。

## License

MIT
