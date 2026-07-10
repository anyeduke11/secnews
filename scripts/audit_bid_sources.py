"""审计当前 bid 源 vs skillhub 50+ 渠道的覆盖度"""
from backend.collectors.bid_collector import BID_SOURCES

CURRENT_DOMAINS = {
    "ccgp.gov.cn",
    "cebpubservice.com",
    "ggzy.gov.cn",
    "zycg.gov.cn",
    "chinabidding.com.cn",
    "cfcpn.com",
    "zcygov.cn",
    "bidcenter.com.cn",
}

# skillhub 列出的 50+ 渠道（按域名）
SKILLHUB_CHANNELS = {
    # P0 国家级 5
    "ccgp.gov.cn", "cebpubservice.com", "ggzy.gov.cn", "zycg.gov.cn", "chinabidding.com.cn",
    # P1 金融 12
    "szse.cn", "sse.com.cn", "cffex.com.cn", "jzcg.com", "cdb.cn",
    "cfid.org.cn", "cfcpn.com", "ziliao.tao", "yifangbao.com", "chinabank.gov.cn", "ybxww.com", "zbscbank.com",
    # P1 政府机构 8
    "ccgp.gov.cn", "ggzy.gov.cn", "jgsw.gov.cn", "nhc.gov.cn", "moe.gov.cn", "stats.gov.cn", "mof.gov.cn", "audit.gov.cn",
    # P1 能源电力 6
    "ecp.sgcc.com.cn", "bidding.csg.cn", "chnenergybidding.com.cn", "sinopec-ec.com", "dlzb.com", "dlnyzb.com",
    # P1 电信运营商 4
    "b2b.10086.cn", "caigou.chinatelecom", "chinaunicombidding.com", "zgdsy.com.cn",
    # P2 医疗教育 4
    "nhc.gov.cn", "moe.gov.cn", "hospital.cn", "edu.cn",
    # P2 交通制造 4
    "mot.gov.cn", "crgc.cc", "crsc.com.cn", "cssc.com.cn",
    # P2 商业聚合 12
    "bidcenter.com.cn", "qianlima.com", "yifangbao.com", "zcygov.cn", "plap.cn",
    "zbj.com", "biaobia.com", "tianyancha.com", "aiqicha.com", "qcc.com",
    "myrich.com", "bidbaobao.com",
    # P3 辅助 5
    "szexgrp.com", "mayitb.com", "industry.gov.cn", "nda.gov.cn", "local-purchase.gov.cn",
}

print(f"当前 BidCollector 源数: {len(BID_SOURCES)}")
print(f"当前覆盖域名: {len(CURRENT_DOMAINS)}")
print(f"SkillHub 推荐渠道: 50+ (5+12+8+6+4+4+4+12+5 = 60)")
print()

# 当前覆盖
covered = CURRENT_DOMAINS & SKILLHUB_CHANNELS
missing = SKILLHUB_CHANNELS - CURRENT_DOMAINS
print(f"已覆盖: {len(covered)} / 60 推荐渠道")
print(f"  {sorted(covered)}")
print()
print(f"未覆盖关键渠道 (按业务线):")
print()

# 按业务线分
P1_finance = {"szse.cn", "sse.com.cn", "cffex.com.cn", "jzcg.com", "cdb.cn", "cfid.org.cn", "cfcpn.com"}
P1_energy = {"ecp.sgcc.com.cn", "bidding.csg.cn", "chnenergybidding.com.cn", "sinopec-ec.com", "dlzb.com", "dlnyzb.com"}
P1_telecom = {"b2b.10086.cn", "caigou.chinatelecom", "chinaunicombidding.com", "zgdsy.com.cn"}
P2_medical_edu = {"nhc.gov.cn", "moe.gov.cn"}
P2_transport = {"mot.gov.cn", "crgc.cc", "crsc.com.cn", "cssc.com.cn"}
P2_commercial = {"qianlima.com", "yifangbao.com", "zcygov.cn", "plap.cn", "zbj.com", "tianyancha.com", "aiqicha.com", "qcc.com", "bidbaobao.com"}
P3_aux = {"szexgrp.com", "mayitb.com", "industry.gov.cn", "nda.gov.cn"}

for name, chans in [
    ("P1 金融 (szse/sse/jzcg/cdb 等)", P1_finance),
    ("P1 能源电力 (ecp.sgcc/bidding.csg/chnenergy)", P1_energy),
    ("P1 电信运营商 (中国移动/电信/联通/广电)", P1_telecom),
    ("P2 医疗教育 (卫健委/教育部)", P2_medical_edu),
    ("P2 交通制造 (交通部/国铁/中车/中船)", P2_transport),
    ("P2 商业聚合 (千里马/乙方宝/政采云/军队)", P2_commercial),
    ("P3 辅助 (深圳/蚂蚁投标/垂直行业)", P3_aux),
]:
    miss = chans - CURRENT_DOMAINS
    print(f"  {name}: 缺 {len(miss)} 个")
    for m in sorted(miss):
        print(f"    - {m}")
    print()
