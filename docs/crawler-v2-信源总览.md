# Crawler v2 信源总览

> **版本**: v1.9
> **日期**: 2026-08-02
> **范围**: 覆盖 8 个分类（AI / AI_SECURITY / SECURITY / FINANCE / STARTUP / BID / GITHUB / TECH），总计 ~100+ 数据源

---

## 一、AI 资讯（7 源）

| # | 源名称 | 类型 | URL | 抓取方式 | 质量分 |
|---|--------|------|-----|---------|--------|
| 1 | HackerNews | RSS | `https://hnrss.org/newest` | RSS feedparser | 80 |
| 2 | 量子位 | HTML | `https://www.qbitai.com/` | crawl4ai 浏览器渲染 | 78 |
| 3 | 36氪AI | HTML | `https://36kr.com/information/AI` | crawl4ai 浏览器渲染 | 75 |
| 4 | 机器之心 | HTML | `https://www.jiqizhixin.com/` | crawl4ai 浏览器渲染 | 78 |
| 5 | AIhot | RSS/JSON | `https://aihot.virxact.com/` | RSS 优先，JSON API 兜底 | 82 |
| 6 | 小互AI | RSS | `https://best.xiaohu.ai/rss.xml` | RSS feedparser | 80 |
| 7 | AGI Hunt | RSS | `https://agihunt.info/feed.xml` | RSS feedparser | 78 |

---

## 二、AI 安全专题（6 源）

| # | 源名称 | 类型 | URL | 抓取方式 | 质量分 |
|---|--------|------|-----|---------|--------|
| 1 | SecurityWeek AI Security | RSS | `https://www.securityweek.com/feed/` | RSS feedparser | 83 |
| 2 | BleepingComputer AI | HTML | `https://www.bleepingcomputer.com/tag/artificial-intelligence/` | aiohttp HTML | 80 |
| 3 | Lil'Log | RSS | `https://lilianweng.github.io/index.xml` | RSS feedparser | 88 |
| 4 | HN AI Security | RSS | `https://hnrss.org/newest?q=AI+security+OR+LLM+vulnerability+OR+prompt+injection+OR+AI+safety` | RSS feedparser | 80 |
| 5 | 安全内参 | HTML | `https://www.secrss.com/` | aiohttp HTML | 78 |
| 6 | FreeBuf AI安全 | HTML | `https://www.freebuf.com/` | aiohttp HTML | 78 |

---

## 三、网络安全（27 源）

### 3.1 国际安全媒体（5 源）

| # | 源名称 | 类型 | URL | 抓取方式 | 质量分 |
|---|--------|------|-----|---------|--------|
| 1 | KrebsOnSecurity | HTML | `https://krebsonsecurity.com/` | aiohttp HTML | 85 |
| 2 | TheHackerNews | RSS | `https://thehackernews.com/feeds/posts/default` | RSS feedparser | 82 |
| 3 | HackRead | HTML | `https://www.hackread.com/` | aiohttp HTML | 72 |
| 4 | Schneier on Security | HTML | `https://www.schneier.com/` | aiohttp HTML | 78 |
| 5 | SecWiki | RSS | `https://www.sec-wiki.com/news/rss` | RSS feedparser | 70 |

### 3.2 中文安全媒体（5 源）

| # | 源名称 | 类型 | URL | 抓取方式 | 质量分 |
|---|--------|------|-----|---------|--------|
| 1 | 安全客 | RSS | `https://api.anquanke.com/data/v1/rss` | RSS feedparser | 75 |
| 2 | FreeBuf | RSS | `https://www.freebuf.com/feed` | RSS feedparser | 75 |
| 3 | 嘶吼 | RSS | `https://www.4hou.com/feed` | RSS feedparser | 70 |
| 4 | 安全内参 | JSON | `https://www.secrss.com/api/articles` | JSON API | 80 |
| 5 | 等级保护网 | HTML | `https://www.djbh.net/` | aiohttp HTML | 82 |

### 3.3 监管机构（5 源）

| # | 源名称 | 类型 | URL | 抓取方式 | 质量分 |
|---|--------|------|-----|---------|--------|
| 1 | 国家金融监督管理总局 | HTML | `https://www.nfra.gov.cn/` | aiohttp HTML | 90 |
| 2 | TC260 信安标委 | HTML | `https://www.tc260.org.cn/` | aiohttp HTML | 82 |
| 3 | CNNVD 国家漏洞库 | HTML | `https://www.cnnvd.org.cn/` | aiohttp HTML | 80 |
| 4 | 奇安信威胁情报 | HTML | `https://ti.qianxin.com/` | aiohttp HTML | 85 |
| 5 | 深信服科技 | HTML | `https://www.sangfor.com.cn/` | aiohttp HTML | 78 |

### 3.4 安全厂商（5 源）

| # | 源名称 | 类型 | URL | 抓取方式 | 质量分 |
|---|--------|------|-----|---------|--------|
| 1 | 绿盟科技 | HTML | `https://www.nsfocus.com/` | aiohttp HTML | 78 |
| 2 | 启明星辰 | RSS | `https://www.gm7.org/feed` | RSS feedparser | 76 |
| 3 | 知道创宇 | HTML | `https://www.knownsec.com/` | aiohttp HTML | 76 |
| 4 | 微步在线(搜狗) | 搜狗微信 | `https://weixin.sogou.com/weixin?type=2&query=微步在线` | sogou 搜索 | 88 |
| 5 | 奇安信威胁情报中心(搜狗) | 搜狗微信 | `https://weixin.sogou.com/weixin?type=2&query=奇安信威胁情报中心` | sogou 搜索 | 87 |

### 3.5 搜狗微信公众号源（7 源）

| # | 源名称 | URL | 搜索关键词 | 质量分 | 上限 |
|---|--------|-----|-----------|--------|------|
| 1 | 微步在线(搜狗) | `weixin.sogou.com` | 微步在线 威胁情报 | 88 | 15 |
| 2 | 奇安信威胁情报中心(搜狗) | `weixin.sogou.com` | 奇安信威胁情报中心 漏洞 | 87 | 15 |
| 3 | 360威胁情报中心(搜狗) | `weixin.sogou.com` | 360威胁情报中心 漏洞 | 85 | 12 |
| 4 | FreeBuf(搜狗) | `weixin.sogou.com` | FreeBuf 漏洞 | 78 | 10 |
| 5 | 安全客(搜狗) | `weixin.sogou.com` | 安全客 漏洞 | 76 | 10 |
| 6 | 看雪论坛(搜狗) | `weixin.sogou.com` | 看雪论坛 漏洞分析 | 74 | 10 |
| 7 | 安全内参(搜狗) | `weixin.sogou.com` | 安全内参 漏洞 | 76 | 10 |

---

## 四、金融资讯（8 源）

| # | 源名称 | 类型 | URL | 抓取方式 | 质量分 |
|---|--------|------|-----|---------|--------|
| 1 | 中国证监会 | HTML | `https://www.csrc.gov.cn/` | aiohttp HTML | 88 |
| 2 | 新浪财经 | HTML | `https://finance.sina.com.cn/` | crawl4ai 浏览器渲染 | 80 |
| 3 | 东方财富 | HTML | `https://www.eastmoney.com/` | crawl4ai 浏览器渲染 | 80 |
| 4 | 华尔街见闻 | HTML | `https://wallstreetcn.com/` | aiohttp HTML | 78 |
| 5 | 雪球 | HTML | `https://xueqiu.com/` | crawl4ai 浏览器渲染 | 75 |
| 6 | 财新网 | HTML | `https://www.caixin.com/` | aiohttp HTML | 80 |
| 7 | 财联社 | HTML | `https://www.cls.cn/telegraph` | ⛔ disabled（SPA 签名 API） | 82 |
| 8 | 金十数据 | JSON | `https://www.jin10.com/flash_newest.js` | aiohttp + JS 解析 | 80 |

---

## 五、创业/独立开发（4 源）

| # | 源名称 | 类型 | URL | 抓取方式 | 质量分 |
|---|--------|------|-----|---------|--------|
| 1 | 36氪 | RSS | `https://36kr.com/feed` | RSS feedparser | 78 |
| 2 | 虎嗅 | HTML | `https://www.huxiu.com/` | aiohttp HTML | 76 |
| 3 | 投资界 | HTML | `https://www.pedaily.cn/` | aiohttp HTML | 75 |
| 4 | IT桔子 | HTML | `https://www.itjuzi.com/` | aiohttp HTML | 72 |

---

## 六、标讯（招标信息，~50 源）

### 6.1 P0 国家级官方平台（5 源）

| # | 源名称 | URL | 质量分 |
|---|--------|-----|--------|
| 1 | 中国政府采购网 | `https://www.ccgp.gov.cn/cggg/zygg/` | 80 |
| 2 | 招标投标公共服务平台 | `https://www.cebpubservice.com/ggxx/` | 80 |
| 3 | 全国公共资源交易平台 | `https://www.ggzy.gov.cn/info/zbgg` | 80 |
| 4 | 中央政府采购网 | `https://www.zycg.gov.cn/freecms/site/zycg/ggxx/info/` | 78 |
| 5 | 中国采购与招标网 | `https://www.chinabidding.com.cn/zbgg/` | 75 |

### 6.2 P1 金融行业（12+ 源）

| # | 源名称 | URL | 质量分 |
|---|--------|-----|--------|
| 1 | 深交所采购信息 | `https://www.szse.cn/disclosure/notice/general/` | 80 |
| 2 | 上交所采购信息 | `https://www.sse.com.cn/services/trading/business/` | 80 |
| 3 | 中金所采购公告 | `https://www.cffex.com.cn/` | 78 |
| 4 | 国家开发银行采购 | `https://www.cdb.cn/` | 78 |
| 5 | 成方金融采购网 | `https://www.cfid.org.cn/` | 76 |
| 6 | 金融采购网 | `https://www.cfcpn.com/` | 75 |
| 7 | 中国人民银行集中采购中心 | `https://jzcg.pbc.gov.cn/` | 80 |
| 8 | 中国采购与招标网-金融频道 | `https://www.chinabidding.com.cn/bidList-0-0-1-0-0-1.html` | 76 |
| 9 | 采招网-金融频道 | `https://www.bidcenter.com.cn/bidlist-0-0-0-0-0-0-0-0-0-0-1-1-0.htm` | 75 |
| 10 | 晨歌招标网 | `https://www.chengezhao.com/` | 72 |
| 11 | 招标网-金融频道 | `https://www.zhaobiao.cn/bidding/list?catId=2` | 72 |
| 12 | 采联网-金融频道 | `https://www.zgzbw.com/list-1.html` | 70 |
| 13 | 中国农业发展银行集中采购 | `https://pms.adbc.com.cn/` | 78 |
| 14 | 银保信 | `https://www.cfxcredit.com/` | 76 |
| 15 | 中国银联采购 | `https://www.chinaunionpay.com/` | 76 |
| 16 | 知了标讯 | `https://www.zhiliaobiaoxun.com/` | 70 |
| 17 | 证保信 | `https://zgzx-pa.com.cn/` | 70 |

### 6.3 P1 能源电力（11 源）

| # | 源名称 | URL | 质量分 |
|---|--------|-----|--------|
| 1 | 国家电网电子商务平台 | `https://ecp.sgcc.com.cn/html/project/index_1.shtml` | 80 |
| 2 | 南方电网采购 | `https://www.bidding.csg.cn/` | 80 |
| 3 | 国家能源采购 | `https://www.chnenergybidding.com.cn/` | 78 |
| 4 | 中石化采购 | `https://www.sinopec-ec.com/` | 76 |
| 5 | 电力招标网 | `https://www.dlzb.com/` | 72 |
| 6 | 电力能源招标网 | `https://www.dlnyzb.com/` | 70 |
| 7 | 华能电子商务平台 | `https://ec.chng.com.cn/` | 78 |
| 8 | 大唐电子商务平台 | `https://www.cdt-ec.com/` | 78 |
| 9 | 华电电子商务平台 | `https://www.chdtp.com/` | 78 |
| 10 | 中化商务电子招投标 | `https://ebid.sinochemitc.com/` | 74 |
| 11 | 深圳阳光采购平台 | `https://ygcg.szexgrp.com/` | 72 |

### 6.4 P1 电信运营商（4 源）

| # | 源名称 | URL | 质量分 |
|---|--------|-----|--------|
| 1 | 中国移动 B2B 采购 | `https://b2b.10086.cn/` | 80 |
| 2 | 中国电信采购 | `https://caigou.chinatelecom.com.cn/` | 78 |
| 3 | 中国联通采购 | `https://www.chinaunicombidding.com/` | 76 |
| 4 | 中国广电采购 | `https://www.zgdsy.com.cn/` | 70 |

### 6.5 P2 医疗教育（4 源）

| # | 源名称 | URL | 质量分 |
|---|--------|-----|--------|
| 1 | 卫健委采购平台 | `https://www.nhc.gov.cn/` | 72 |
| 2 | 教育部政府采购 | `https://www.moe.gov.cn/` | 70 |
| 3 | 采招网-医疗频道 | `https://www.bidcenter.com.cn/bidlist-0-0-0-0-0-0-0-0-0-0-3-1-0.htm` | 72 |
| 4 | 采招网-教育频道 | `https://www.bidcenter.com.cn/bidlist-0-0-0-0-0-0-0-0-0-0-4-1-0.htm` | 70 |

### 6.6 P2 交通制造（4 源）

| # | 源名称 | URL | 质量分 |
|---|--------|-----|--------|
| 1 | 交通运输部采购 | `https://www.mot.gov.cn/` | 72 |
| 2 | 国铁集团采购平台 | `https://www.crgc.cc/` | 70 |
| 3 | 中车集团采购 | `https://www.crsc.com.cn/` | 70 |
| 4 | 中船集团采购 | `https://www.cssc.com.cn/` | 70 |

### 6.7 P2 商业聚合（12+ 源）

| # | 源名称 | URL | 质量分 |
|---|--------|-----|--------|
| 1 | 采招网 | `https://www.bidcenter.com.cn/` | 70 |
| 2 | 千里马招标网 | `https://www.qianlima.com/` | 68 |
| 3 | 乙方宝 | `https://www.yifangbao.com/` | 66 |
| 4 | 政采云 | `https://www.zcygov.cn/` | 72 |
| 5 | 军队采购网 | `https://www.plap.cn/` | 74 |
| 6 | 中招联合招标采购 | `https://www.zbj.com/` | 65 |
| 7 | 招标网 | `https://www.zhaobiao.cn/` | 68 |
| 8 | 比比招标 | `https://www.chengezhao.com/zfcg/` | 67 |
| 9 | 采联网 | `https://www.zgzbw.com/` | 67 |
| 10 | 招标信息港 | `https://www.bidnews.cn/` | 66 |
| 11 | 易招标 | `https://www.ebnew.com/` | 65 |
| 12 | 深圳公共资源交易 | `https://www.szexgrp.com/` | 70 |
| 13 | 招标采购导航网 | `https://www.okcis.cn/` | 68 |
| 14 | 比地招标网 | `https://www.bidizhaobiao.com/` | 66 |
| 15 | 元博招标网 | `https://www.bidchance.com/` | 66 |
| 16 | 中国国际招标网 | `https://chinabidding.mofcom.gov.cn/` | 72 |
| 17 | 中国政府采购招标网 | `https://www.chinabidding.org.cn/` | 66 |

### 6.8 P3 辅助（2 源）

| # | 源名称 | URL | 质量分 |
|---|--------|-----|--------|
| 1 | 蚂蚁投标 | `https://www.mayitb.com/` | 60 |
| 2 | 中国外汇交易中心 | `https://www.chinamoney.com.cn/` | 68 |

---

## 七、GitHub 开源（3 源）

| # | 源名称 | 类型 | URL | 抓取方式 | 质量分 |
|---|--------|------|-----|---------|--------|
| 1 | GitHub Trending | HTML | `https://github.com/trending` | crawl4ai 浏览器渲染 | 82 |
| 2 | Star History | HTML | `https://github.com/star-history/star-history` | crawl4ai 浏览器渲染 | 78 |
| 3 | TopHub GitHub 热榜 | HTML | `https://tophub.today/n/rYqoXQ8vOD` | aiohttp HTML | 76 |

---

## 八、科技资讯（3 源）

| # | 源名称 | 类型 | URL | 抓取方式 | 质量分 |
|---|--------|------|-----|---------|--------|
| 1 | IT之家 | HTML | `https://www.ithome.com/list/` | aiohttp HTML | 80 |
| 2 | HackerNews | JSON API | `https://hacker-news.firebaseio.com/v0/topstories.json` | aiohttp JSON | 85 |
| 3 | Reddit | JSON API | `https://www.reddit.com/r/all/top.json` | aiohttp JSON | 80 |

---

## 抓取方式说明

| 方式 | 说明 | 适用场景 |
|------|------|---------|
| aiohttp HTML | 默认 HTTP GET + 正则/选择器解析 | 大多数静态 HTML 页面 |
| RSS feedparser | `feedparser.parse(bytes)` 解析 RSS/Atom XML | 提供 RSS 输出的源 |
| JSON API | 直接请求 JSON 端点，结构化解析 | 提供 JSON API 的源 |
| crawl4ai | Playwright 浏览器渲染 + JS 执行 | 反爬 / SPA 页面 |
| sogou 搜索 | 搜狗微信搜索，模拟搜索请求 | 微信公众号文章 |

> **注意**: 所有 HTTP 请求统一走 `BackendSession`（httpx async），内置代理、重试（指数退避，最多 3 次）、限速、超时（连接 10s + 读取 30s）控制。