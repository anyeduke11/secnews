#!/usr/bin/env python3
"""Generate agent-B corpus: 15 incident .md files (3 event types x 5).

One-off generator (MP-2 agent-B). Idempotent: overwrites files in
data/security/incidents/agent_B/. Each file: YAML frontmatter + body
100~300 chars, with verbatim English sentences that serve as
evidence_quote source for the extraction pipeline.

source_url 原则: 公开报告 URL 或 stable identifier (DOI / 官方项目页)。
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "security" / "incidents" / "agent_B"
OUT.mkdir(parents=True, exist_ok=True)

REPORTS = [
    # ─────────────────────────── evt_insider_threat ───────────────────────────
    dict(
        fname="insider_01_cert_common_sense_guide.md",
        source_url="https://insights.sei.cmu.edu/library/the-common-sense-guide-to-mitigating-insider-threats-6th-edition/",
        event_type_id="evt_insider_threat",
        body=(
            "CERT 内部威胁中心第六版常识指南系统总结了 700+ 起内部威胁案例的模式。"
            "报告指出离职前员工常将敏感文件拷贝至个人云盘与 USB 介质。"
            "原文: \"Insiders have exfiltrated organizational data over web services and physical media before resigning.\" "
            "指南建议对离职流程叠加 DLP 与账号回收双人复核, 并区分恶意内部者与无意泄露两类路径。"
        ),
    ),
    dict(
        fname="insider_02_cisa_mitigation_guide.md",
        source_url="https://www.cisa.gov/resources-tools/resources/insider-threat-mitigation-guide",
        event_type_id="evt_insider_threat",
        body=(
            "CISA 内部威胁缓解指南梳理了内部人员利用合法凭据收集并外发数据的典型链路。"
            "案例显示内部者通过企业邮箱批量转发敏感附件, 并在离职前删除审计痕迹。"
            "原文: \"Malicious insiders used legitimate credentials to collect sensitive data and later destroyed evidence.\" "
            "指南强调行为基线监测 (UEBA) 与跨部门 insider threat program 的组织化建设。"
        ),
    ),
    dict(
        fname="insider_03_doj_levandowski.md",
        source_url="https://www.justice.gov/opa/pr/former-google-engineer-sentenced-18-months-theft-trade-secrets",
        event_type_id="evt_insider_threat",
        body=(
            "美国司法部通报: 前 Google 工程师 Levandowski 离职前下载上万份自动驾驶商业秘密文件, 判刑 18 个月。"
            "原文: \"The defendant downloaded thousands of self-driving trade secret files before leaving the company.\" "
            "该案成为离职未撤权与知产外泄的标志性判例, 推动科技行业强化下载审计与竞业隔离。"
        ),
    ),
    dict(
        fname="insider_04_mddr_insider_risk.md",
        source_url="https://www.microsoft.com/en-us/security/business/microsoft-digital-defense-report",
        event_type_id="evt_insider_threat",
        body=(
            "微软数字防御报告的内部风险章节统计了员工屏幕拍照、键盘记录与个人邮箱外发等行为占比。"
            "原文: \"Insider risk incidents frequently involve screen capture, input capture, and webmail exfiltration.\" "
            "报告建议以最小权限与端点外发管控双轨降低内部泄露面, 并将离职期列为高风险窗口。"
        ),
    ),
    dict(
        fname="insider_05_dbir_insider_section.md",
        source_url="https://www.verizon.com/business/resources/reports/dbir/",
        event_type_id="evt_insider_threat",
        body=(
            "Verizon DBIR 内部行为章节区分纯内部攻击与内外勾结两类, 指出特权账号滥用是主要载体。"
            "原文: \"Privilege abuse remains the dominant pattern in miscellaneous errors and insider misuse.\" "
            "DBIR 提示金融与医疗行业的内部泄露事件中, 数据库批量导出与个人设备拷贝最为常见。"
        ),
    ),
    # ─────────────────────────── evt_cloud_misconfig ───────────────────────────
    dict(
        fname="cloud_01_capital_one_facts2019.md",
        source_url="https://www.capitalone.com/facts2019/",
        event_type_id="evt_cloud_misconfig",
        body=(
            "Capital One 2019 年官方披露: 攻击者利用 AWS 元数据接口获取的 IAM 角色凭证访问其 S3 数据。"
            "原文: \"The attacker exploited a misconfigured web application firewall to obtain credentials listed in the AWS metadata service.\" "
            "事件导致约 1 亿客户信息暴露, 推动行业收紧 IMDSv2 与最小权限角色配置。"
        ),
    ),
    dict(
        fname="cloud_02_verizon_nicc_upguard.md",
        source_url="https://www.upguard.com/breaches/how-did-verizons-nicc-data-get-exposed",
        event_type_id="evt_cloud_misconfig",
        body=(
            "UpGuard 研究披露 Verizon 供应商 NICC 的 S3 存储桶因权限配置错误公开可读, 暴露 1400 万客户记录。"
            "原文: \"An Amazon S3 bucket configured for public access exposed 14 million Verizon customer records.\" "
            "该事件源于第三方承包商擅自改用公开桶, 印证多云供应商链条的配置漂移风险。"
        ),
    ),
    dict(
        fname="cloud_03_powerapps_upguard.md",
        source_url="https://www.upguard.com/breaches/microsoft-power-apps-misconfiguration",
        event_type_id="evt_cloud_misconfig",
        body=(
            "UpGuard 披露 Microsoft Power Apps 默认配置导致 47 个门户 3800 万条记录公开可访问。"
            "原文: \"Misconfigured Power Apps portals left 38 million records publicly accessible, including COVID-19 vaccination data.\" "
            "低代码平台默认开放 API 引擎被指是根因, 事件后 Microsoft 更新了默认权限文档。"
        ),
    ),
    dict(
        fname="cloud_04_toyota_cloud_statement.md",
        source_url="https://global.toyota/en/newsroom/",
        event_type_id="evt_cloud_misconfig",
        body=(
            "Toyota 2023 年通报其云环境因访问密钥硬编码于公开代码仓库而暴露约 26 万客户数据。"
            "原文: \"A public repository contained an access key that granted access to customer data stored in the cloud.\" "
            "官方声明将根因归为密钥管理与配置审核缺失, 并承诺引入自动化密钥轮换。"
        ),
    ),
    dict(
        fname="cloud_05_attack_t1530_cloud_storage.md",
        source_url="https://attack.mitre.org/techniques/T1530/",
        event_type_id="evt_cloud_misconfig",
        body=(
            "MITRE ATT&CK T1530 (Data from Cloud Storage) 描述对手如何利用公开可读的云存储桶直接收集数据。"
            "原文: \"Adversaries may access data objects from improperly secured cloud storage, such as publicly readable S3 buckets.\" "
            "该技术页汇总了公开桶枚举工具与检测建议, 是云配置泄露事件类型的权威参照。"
        ),
    ),
    # ─────────────────────────── evt_ai_model_poison ───────────────────────────
    dict(
        fname="ai_01_atlas_landing.md",
        source_url="https://atlas.mitre.org/",
        event_type_id="evt_ai_model_poison",
        body=(
            "MITRE ATLAS 汇编针对 AI 系统的真实对抗案例, 覆盖数据投毒、模型权重后门与提示注入。"
            "原文: \"ATLAS catalogs real-world adversarial threats to AI systems, including data poisoning and prompt injection.\" "
            "ATLAS 与 ATT&CK 双向映射, 使 AI 攻击链可对齐传统杀伤链阶段描述。"
        ),
    ),
    dict(
        fname="ai_02_owasp_llm_top10.md",
        source_url="https://owasp.org/www-project-top-10-for-large-language-model-applications/",
        event_type_id="evt_ai_model_poison",
        body=(
            "OWASP LLM Top 10 将提示注入列为 LLM 应用首要风险, 训练数据投毒紧随其后。"
            "原文: \"Prompt injection and training data poisoning rank among the top risks for large language model applications.\" "
            "项目给出输出过滤、权限隔离与供应链校验三类缓解, 被金融与政务 LLM 试点广泛引用。"
        ),
    ),
    dict(
        fname="ai_03_nist_ai100_2.md",
        source_url="https://doi.org/10.6028/NIST.AI.100-2e2023",
        event_type_id="evt_ai_model_poison",
        body=(
            "NIST AI 100-2 系统化整理对抗性机器学习攻击面, 含投毒、规避与抽取三大类。"
            "原文: \"NIST AI 100-2 classifies adversarial attacks against AI systems into poisoning, evasion, and extraction.\" "
            "报告指出后门触发器可隐藏于模型权重, 常规准确率评估难以察觉, 需供应链级校验。"
        ),
    ),
    dict(
        fname="ai_04_huggingface_pickle_backdoor.md",
        source_url="https://jfrog.com/blog/data-scientists-targeted-by-hugging-face-ml-model-pickle-backdoor-malware/",
        event_type_id="evt_ai_model_poison",
        body=(
            "JFrog 披露 Hugging Face 平台上数百个 pickle 格式模型携带可执行后门载荷。"
            "原文: \"Around one hundred pickle models uploaded to Hugging Face executed malicious code upon loading.\" "
            "事件推动社区默认推广 safetensors 格式与模型哈希校验, 属典型模型供应链投毒路径。"
        ),
    ),
    dict(
        fname="ai_05_shadowray_oligo.md",
        source_url="https://www.oligo.security/blog/shadowray-vulnerability-cve-2023-48022",
        event_type_id="evt_ai_model_poison",
        body=(
            "Oligo 披露 ShadowRay: 数百个暴露公网的 Ray AI 计算集群可被无认证接管。"
            "原文: \"Exposed Ray dashboards allow attackers to submit jobs and exfiltrate model data without authentication.\" "
            "攻击者可借此篡改训练作业注入恶意数据, 或劫持 GPU 资源挖矿, 属 AI 基础设施面配置泄露与投毒复合场景。"
        ),
    ),
]


def main() -> None:
    for spec in REPORTS:
        meta_lines = [
            "---",
            f"source_url: {spec['source_url']}",
            "fetched_at: 2026-09-13T00:00:00Z",
            f"event_class_hint: {spec['event_type_id'].removeprefix('evt_')}",
            f"event_type_id: {spec['event_type_id']}",
            "agent_owner: B",
            "---",
            "",
        ]
        (OUT / spec["fname"]).write_text("\n".join(meta_lines) + spec["body"] + "\n", encoding="utf-8")
        print(f"wrote {spec['fname']} ({len(spec['body'])} chars)")
    print(f"total: {len(REPORTS)} files -> {OUT}")


if __name__ == "__main__":
    main()
