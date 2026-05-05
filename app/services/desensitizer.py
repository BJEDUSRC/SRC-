"""
数据脱敏服务模块

基于LangChain大模型的智能脱敏服务。
"""

from typing import Dict, Tuple, Optional, List
import logging
import time
import re

from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import RunnablePassthrough

from app.services.llm_service import LLMService
from app.services.url_desensitization_service import get_url_desensitization_service
from app.utils.logger import get_logger
from app.utils.llm_logger import get_llm_logger
from app.config import settings

logger = get_logger(__name__)


class Desensitizer:
    """
    数据脱敏服务类
    
    使用大模型进行智能脱敏，处理各类敏感信息。
    """
    
    # 保留空的PATTERNS用于兼容性
    PATTERNS = {}
    
    # 敏感信息类型定义（仅用于描述，供大模型参考）
    SENSITIVE_TYPES = [
        "IP地址", "身份证号", "手机号", "邮箱", "银行卡号", 
        "地址", "姓名", "组织机构", "API密钥", "Token",
        "ICP备案号", "公安备案号", "学校机构", "教育单位",
        "其他敏感信息"
    ]
    
    # LLM脱敏提示词模板（增强版）
    DESENSITIZE_PROMPT_TEMPLATE = """你是一位具有强大洞察力的数据安全和隐私保护专家。
请务必按照以下规则进行数据脱敏操作（超重点，一定要遵守）：
  为了体现报告的真实性，禁止使用任何模糊形式进行替换，例如：
    - `XXX`、`xxx`、`***`
    - `某某`、`某单位`、`某公司`
    - `**`（作为占位符时）
    - `[待补充]`、`[待填写]`
    - 任何形式的占位符标记
  脱敏白名单（仅以下内容不进行任何脱敏）：
    1、漏洞详情（不包含URL）、漏洞单位
    2、版权所有：北京教育行业SRC平台备案号：京ICP备05083811号公安备案号：1104021101050007
  注意：白名单仅保护文字内容，URL、IP地址、个人信息等仍按敏感信息处理
  
  采用动态脱敏策略
    - **高敏感**：完全替换
    - **中敏感**：一半替换（选择一半内容进行替换）
    - **低敏感**：少量替换（选择一两个进行替换）
    敏感信息分类示例（请灵活扩充）：
    手机号：中敏感，替换一半，例如：17838965235->17838957144（替换后一半）,17838965235->17849875235（替换中间一半）
    姓名：高敏感，完全替换，例如：王兴->李敏
    身份证号：高敏感，完全替换，例如：411381255669568745->654326545896542658
    URL（任何字符中含URL的都要替换）：中敏感，替换路径，例如：
      http://www.kugou.cn/bucc/sfsf/bfds/mlok替换为http://www.kugou.cn/cfdd/bkbk/bfds/mlok
      http://www.mkjh.top/vbnn/plop/zxsw/weqq替换为http://www.mkjh.top/xdee/vfpo/zxsw/weqq
      http://www.caad.com/sdde/wyui/jlfg/pprr替换为http://www.caad.com/njjh/njkl/lklu/pprr
    ...
  在动态脱敏策略的基础上:
    1、识别出敏感信息后,为需要替换的部分进行替换,替换为同类型的信息
    2、对需要替换的敏感信息进行深入分析,了解它的结构与特性,替换后的数据尽量像原数据一样真实
    3、根据敏感信息所在的场景进行智能替换,替换后尽可能符合原场景
    4、数据替换后尽可能使报告看起来真实、专业且完整
  限定输出格式
    - **直接输出**：返回脱敏后的文本，保持原格式，不添加解释
    - **保持结构**：不改变文本结构和段落，只替换敏感内容

  **特别重要：URL脱敏说明**
    1、如果提供了URL路径段脱敏映射规则，请严格按照规则处理
      - 例如：如果规则要求 `sousou` -> `bccbcc`，则所有包含 `sousou` 的URL路径段都要替换为 `bccbcc`
    2、对于未提供映射规则的URL路径段，进行正常脱敏处理（即上面动态脱敏策略）


基于以上规则，查找敏感信息并按规则替换：
  智能识别：
    你需要运用专业判断，识别任何可能泄露个人隐私、企业机密、系统安全的信息，主动发现潜在的敏感数据。
  上下文感知：
    - 分析文档类型和业务场景，识别特定领域的敏感信息
  专业安全判断：
    - 任何可能被恶意利用的信息
    - 真实的攻击目标、具体机构名称、系统版本等高风险信息


  常见敏感信息类型（请灵活扩展）：

    1. 网络信息
      - IPv4地址
      - IPv6地址
      - MAC地址
      - 内网域名
      - 端口号
      - 主机名

    2. 个人身份信息
      - 身份证号
      - 护照号
      - 手机号
      - 座机号
      - 车牌号

    3. 联系方式
      - 邮箱
      - QQ号
      - 微信号

    4. 地址信息
      - 家庭住址
      - 工作地址
      - GPS坐标

    5. 金融信息
      - 银行卡号
      - 支付宝账号
      - 信用卡CVV
      - 交易流水号

    6. 认证凭证
      - 密码
      - Token
      - API密钥
      - Session ID
      - JWT Token
      - Cookie值

    7. 组织信息
      - 统一社会信用代码
      - 组织机构代码
      - 营业执照号

    8. 个人隐私
      - 姓名
      - 年龄
      - 生日
      - 学号/工号

    9. 敏感URL和参数
      - URL中的token/password/key等参数
      - 认证头(Authorization)
      - Cookie字符串

    10. 其他敏感信息
      - Base64编码的长字符串（可能是密钥）
      - 看起来像密钥的随机字符串（长度>20）
      - 数据库连接字符串
      - 文件路径中的用户名

---

**原始文本：**

{text}

{url_mappings}

---

**脱敏后文本：**"""
    
    def __init__(self, llm_service: Optional[LLMService] = None, enable_llm: bool = True, llm_priority: bool = True):
        """
        初始化脱敏服务（仅使用LLM）
        
        Args:
            llm_service: LLM服务实例，如果为None则创建新实例
            enable_llm: 是否启用LLM脱敏功能（默认True）
            llm_priority: 保留参数，用于兼容性
        """
        self.enable_llm = enable_llm
        self.llm_service = llm_service
        self.llm_priority = True  # 始终LLM优先
        self.chain = None
        
        # 初始化URL脱敏映射服务
        self.url_desensitization_service = get_url_desensitization_service()
        
        # 创建LangChain的Prompt模板
        self.prompt = PromptTemplate(
            input_variables=["text", "url_mappings"],
            template=self.DESENSITIZE_PROMPT_TEMPLATE
        )
        
        # 初始化LLM和Chain
        # LangChain 1.2: 使用 LCEL (LangChain Expression Language) 替代 LLMChain
        if enable_llm:
            try:
                if self.llm_service is None:
                    self.llm_service = LLMService()
                
                llm = self.llm_service.get_llm()
                
                # LangChain 1.2: 使用 LCEL 构建链
                # prompt | llm 是新的链式调用方式
                self.chain = self.prompt | llm
                
                logger.info("脱敏服务初始化成功（LLM模式）")
            except Exception as e:
                logger.error(f"LLM初始化失败: {e}")
                self.enable_llm = False
                raise ValueError(f"LLM脱敏服务初始化失败: {e}")
        else:
            logger.warning("脱敏服务未启用LLM，无法进行脱敏")
    
    def _regex_desensitize(self, text: str) -> Tuple[str, Dict[str, int]]:
        """
        正则表达式脱敏（已废弃，保留用于兼容性）
        
        Args:
            text: 原始文本
            
        Returns:
            (原文本, 空字典)
        """
        # 不再使用正则脱敏，直接返回原文本
        logger.debug("正则脱敏已禁用，跳过")
        return text, {}
    
    async def _llm_desensitize(self, text: str) -> Dict[str, any]:
        """
        使用LLM进行深度脱敏
        
        Args:
            text: 原始文本（通常已经过正则预处理）
            
        Returns:
            包含脱敏结果和元数据的字典
        """
        # 记录开始时间
        start_time = time.time()
        llm_logger = get_llm_logger()
        
        if not self.enable_llm or self.chain is None:
            logger.warning("LLM未启用，跳过LLM脱敏")
            result = {
                "text": text,
                "tokens_used": 0,
                "success": False,
                "error": "LLM未启用"
            }
            
            # 记录失败的对话
            processing_time = time.time() - start_time
            llm_logger.log_conversation(
                input_text=text,
                output_text=None,
                success=False,
                tokens_used=0,
                method="llm_disabled",
                error_message="LLM未启用",
                processing_time=processing_time,
                extra_info={"reason": "LLM chain not initialized"}
            )
            
            return result
        
        desensitized_text = None
        total_tokens = 0
        error_message = None
        
        try:
            # 提取文本中的URL并获取已存在的映射
            # 改进的URL正则表达式，匹配更多格式
            # 支持中文冒号、英文冒号、空格等不同格式
            url_with_prefix_pattern = r'(?:(?:漏洞URL|URL|链接|网址)[：:](?:\s*|\s*`*)|(?:^|\s))(https?://[\w\-._~:/?#\[\]@!$&\'()*+,;=.]+)'
            
            # 提取原始URL
            original_matches = re.findall(url_with_prefix_pattern, text)
            urls = [match for match in original_matches]
            
            # 收集已存在的URL路径段映射
            existing_mappings = {}
            for url in urls:
                mappings = self.url_desensitization_service.get_existing_mappings_for_url(url)
                existing_mappings.update(mappings)
            
            # 检查文本长度，如果过长需要分块
            token_count = self.llm_service.get_token_count(text)
            logger.info(f"🔍 LLM脱敏处理，文本token数: {token_count}")
            
            if token_count > 3000:
                logger.info(f"文本过长({token_count} tokens)，进行分块处理")
                
                # 分块处理
                chunks = self.llm_service.split_text_by_tokens(text, max_tokens=3000)
                
                # 为每个分块准备提示词，包含URL映射信息
                enhanced_chunks = []
                for chunk in chunks:
                    if existing_mappings:
                        mappings_str = "\n" + "\n".join([f"- {k} -> {v}" for k, v in existing_mappings.items()])
                        enhanced_chunk = chunk + f"\n\n---\n\nURL路径段脱敏映射规则：{mappings_str}"
                    else:
                        # 没有已存在的映射，不需要添加额外说明
                        enhanced_chunk = chunk
                    enhanced_chunks.append(enhanced_chunk)
                
                results = await self.llm_service.batch_ainvoke(
                    prompts=enhanced_chunks,
                    system_message="你是数据脱敏专家，请严格按照规则脱敏文本。"
                )
                
                # 清理每个结果的思考过程
                cleaned_results = []
                for r in results:
                    cleaned = self._clean_thinking_process(r)
                    cleaned_results.append(cleaned)
                
                desensitized_text = "\n\n".join(cleaned_results)
                total_tokens = sum(self.llm_service.get_token_count(r) for r in cleaned_results)
                
                # 记录分块处理的额外信息
                extra_info = {
                    "processing_mode": "chunked",
                    "chunk_count": len(chunks),
                    "original_tokens": token_count,
                    "chunk_size": 3000,
                    "url_mappings_used": len(existing_mappings)
                }
                
            else:
                # 单次处理，添加URL映射信息
                logger.info("🧠 调用LLM进行单次脱敏...")
                
                # 准备提示词输入，包含URL映射信息
                if existing_mappings:
                    mappings_str = "\n" + "\n".join([f"- {k} -> {v}" for k, v in existing_mappings.items()])
                    url_mappings_text = f"\n\n---\n\nURL路径段脱敏映射规则：{mappings_str}"
                else:
                    # 没有已存在的映射，不需要添加额外说明
                    url_mappings_text = ""
                
                result = await self.chain.ainvoke({"text": text, "url_mappings": url_mappings_text})
                # 结果可能是AIMessage对象，需要提取content
                desensitized_text = result.content if hasattr(result, 'content') else str(result).strip()
                # 清理思考过程
                desensitized_text = self._clean_thinking_process(desensitized_text)
                total_tokens = token_count
                
                extra_info = {
                    "processing_mode": "single",
                    "input_tokens": token_count,
                    "url_mappings_used": len(existing_mappings)
                }
            
            # 提取新的URL映射并更新到数据库
            if desensitized_text:
                new_mappings = self._extract_url_mappings(text, desensitized_text)
                if new_mappings:
                    logger.info(f"发现新的URL路径段映射: {len(new_mappings)} 条")
                    self.url_desensitization_service.add_maps_batch(new_mappings)
            
            # 计算处理时间
            processing_time = time.time() - start_time
            
            # 记录成功的对话
            llm_logger.log_conversation(
                input_text=text,
                output_text=desensitized_text,
                success=True,
                tokens_used=total_tokens,
                method="llm_async",
                processing_time=processing_time,
                extra_info=extra_info
            )
            
            logger.info(f"✅ LLM脱敏成功，耗时: {processing_time:.2f}s，tokens: {total_tokens}")
            
            return {
                "text": desensitized_text,
                "tokens_used": total_tokens,
                "success": True
            }
            
        except Exception as e:
            error_message = str(e)
            processing_time = time.time() - start_time
            
            logger.error(f"LLM脱敏失败: {e}", exc_info=True)
            
            # 记录失败的对话
            llm_logger.log_conversation(
                input_text=text,
                output_text=desensitized_text,
                success=False,
                tokens_used=total_tokens,
                method="llm_async",
                error_message=error_message,
                processing_time=processing_time,
                extra_info={"exception_type": type(e).__name__}
            )
            
            return {
                "text": text,  # 失败时返回原文
                "tokens_used": total_tokens,
                "success": False,
                "error": error_message
            }
    
    async def desensitize(
        self,
        text: str,
        use_regex: bool = False,  # 保留参数用于兼容性，但不使用
        use_llm: bool = True,
        llm_first: bool = None  # 保留参数用于兼容性
    ) -> Dict[str, any]:
        """
        智能脱敏流程（仅使用LLM）
        
        Args:
            text: 原始文本
            use_regex: 保留参数用于兼容性，实际不使用
            use_llm: 是否使用LLM智能脱敏
            llm_first: 保留参数用于兼容性
            
        Returns:
            脱敏结果字典，包含:
            {
                "desensitized_text": "脱敏后的文本",
                "regex_stats": {},  # 始终为空
                "llm_tokens": 1234,
                "llm_success": True,
                "method": "llm"
            }
        """
        logger.info(f"开始LLM智能脱敏，文本长度: {len(text)} 字符")
        
        result = {
            "desensitized_text": text,
            "regex_stats": {},
            "llm_tokens": 0,
            "llm_success": False,
            "method": "none"
        }
        
        if not use_llm or not self.enable_llm or self.chain is None:
            logger.warning("LLM脱敏未启用或不可用")
            return result
        
        # 使用LLM进行脱敏
        logger.info("🧠 LLM智能脱敏...")
        llm_result = await self._llm_desensitize(text)
        
        if llm_result["success"]:
            result["desensitized_text"] = llm_result["text"]
            result["llm_tokens"] = llm_result["tokens_used"]
            result["llm_success"] = True
            result["method"] = "llm"
            logger.info(f"✅ LLM智能脱敏完成，使用 {llm_result['tokens_used']} tokens")
        else:
            logger.error(f"❌ LLM脱敏失败: {llm_result.get('error', '未知错误')}")
        
        logger.info(f"🎉 智能脱敏处理完成，方法: {result['method']}")
        return result
    
    def desensitize_sync(
        self,
        text: str,
        use_regex: bool = False,  # 保留参数用于兼容性，但不使用
        use_llm: bool = True
    ) -> Dict[str, any]:
        """
        同步版本的智能脱敏（仅使用LLM）
        
        Args:
            text: 原始文本
            use_regex: 保留参数用于兼容性，实际不使用
            use_llm: 是否使用LLM智能脱敏
            
        Returns:
            脱敏结果字典
        """
        logger.info(f"🚀 开始同步LLM智能脱敏，文本长度: {len(text)} 字符")
        
        result = {
            "desensitized_text": text,
            "regex_stats": {},
            "llm_tokens": 0,
            "llm_success": False,
            "method": "none"
        }
        
        if not use_llm or not self.enable_llm or self.chain is None:
            logger.warning("LLM脱敏未启用或不可用")
            return result
        
        # 使用LLM进行脱敏
        logger.info("🧠 LLM智能脱敏（同步模式）...")
        
        start_time = time.time()
        llm_logger = get_llm_logger()
        desensitized_text = None
        estimated_tokens = 0
        existing_mappings = {}
        
        try:
            # 提取文本中的URL并获取已存在的映射
            # 改进的URL正则表达式，匹配更多格式
            # 支持中文冒号、英文冒号、空格等不同格式
            url_with_prefix_pattern = r'(?:(?:漏洞URL|URL|链接|网址)[：:](?:\s*|\s*`*)|(?:^|\s))(https?://[\w\-._~:/?#\[\]@!$&\'()*+,;=.]+)'
            
            # 提取原始URL
            original_matches = re.findall(url_with_prefix_pattern, text)
            urls = [match for match in original_matches]
            
            # 收集已存在的URL路径段映射
            for url in urls:
                mappings = self.url_desensitization_service.get_existing_mappings_for_url(url)
                existing_mappings.update(mappings)
            
            # 准备提示词输入，包含URL映射信息
            if existing_mappings:
                mappings_str = "\n" + "\n".join([f"- {k} -> {v}" for k, v in existing_mappings.items()])
                url_mappings_text = f"\n\n---\n\nURL路径段脱敏映射规则：{mappings_str}"
            else:
                # 没有已存在的映射，不需要添加额外说明
                url_mappings_text = ""
            
            llm_result = self.chain.invoke({"text": text, "url_mappings": url_mappings_text})
            desensitized_text = llm_result.content if hasattr(llm_result, 'content') else str(llm_result).strip()
            # 清理思考过程
            desensitized_text = self._clean_thinking_process(desensitized_text)
            
            result["desensitized_text"] = desensitized_text
            result["llm_success"] = True
            result["method"] = "llm"
            
            # 估算token使用量
            estimated_tokens = len(desensitized_text) // 4
            result["llm_tokens"] = estimated_tokens
            
            # 提取新的URL映射并更新到数据库
            if desensitized_text:
                new_mappings = self._extract_url_mappings(text, desensitized_text)
                if new_mappings:
                    logger.info(f"发现新的URL路径段映射: {len(new_mappings)} 条")
                    self.url_desensitization_service.add_maps_batch(new_mappings)
            
            processing_time = time.time() - start_time
            
            # 记录成功的LLM对话
            llm_logger.log_conversation(
                input_text=text,
                output_text=desensitized_text,
                success=True,
                tokens_used=estimated_tokens,
                method="llm_sync",
                processing_time=processing_time,
                extra_info={
                    "sync_mode": True,
                    "input_length": len(text),
                    "output_length": len(desensitized_text),
                    "url_mappings_used": len(existing_mappings)
                }
            )
            
            logger.info(f"✅ LLM智能脱敏完成，估算使用 {estimated_tokens} tokens，耗时: {processing_time:.2f}s")
                        
        except Exception as e:
            error_message = str(e)
            processing_time = time.time() - start_time
            
            logger.error(f"❌ LLM脱敏失败: {e}")
            
            # 记录失败的LLM对话
            llm_logger.log_conversation(
                input_text=text,
                output_text=desensitized_text,
                success=False,
                tokens_used=estimated_tokens,
                method="llm_sync",
                error_message=error_message,
                processing_time=processing_time,
                extra_info={
                    "sync_mode": True,
                    "exception_type": type(e).__name__
                }
            )
            
            # 将错误信息添加到结果中，供调用方判断
            result["error"] = error_message
        
        logger.info(f"🎉 同步智能脱敏完成，方法: {result['method']}")
        return result
    
    def validate_desensitization(self, original: str, desensitized: str) -> Dict[str, any]:
        """
        验证脱敏效果
        
        检查脱敏后的文本中是否还存在敏感信息。
        
        Args:
            original: 原始文本
            desensitized: 脱敏后的文本
            
        Returns:
            验证结果字典
        """
        warnings = []
        suggestions = []
        
        # 计算文本变化率
        reduction_ratio = 1 - len(desensitized) / len(original) if original else 0
        
        # 评估安全等级（基于文本变化）
        if reduction_ratio > 0.1:
            security_level = "high"
            is_safe = True
        elif reduction_ratio > 0.05:
            security_level = "medium"
            is_safe = True
            suggestions.append("文本变化适中，建议人工复查确认")
        else:
            security_level = "low"
            is_safe = False
            warnings.append("文本变化较小，可能脱敏不充分")
            suggestions.append("建议检查是否有敏感信息未被识别")
        
        result = {
            "is_safe": is_safe,
            "security_level": security_level,
            "remaining_sensitive": {},
            "reduction_ratio": reduction_ratio,
            "total_issues": 0,
            "warnings": warnings,
            "suggestions": suggestions
        }
        
        logger.info(f"脱敏验证完成 - 安全等级: {security_level}, 文本变化率: {reduction_ratio:.2%}")
        
        return result
    
    def get_sensitive_info_summary(self, text: str) -> Dict[str, any]:
        """
        分析文本中的敏感信息分布
        
        Args:
            text: 原始文本
            
        Returns:
            敏感信息统计字典
        """
        # 简单统计（无正则）
        summary = {
            "total_sensitive_count": 0,
            "sensitive_types": {},
            "risk_level": "medium",
            "recommendations": ["建议使用LLM智能脱敏处理"]
        }
        
        # 基于文本长度评估风险等级
        text_length = len(text)
        if text_length > 5000:
            summary["risk_level"] = "high"
            summary["recommendations"].append("文本较长，建议进行脱敏处理")
        elif text_length > 1000:
            summary["risk_level"] = "medium"
        else:
            summary["risk_level"] = "low"
        
        logger.info(f"敏感信息分析完成 - 风险等级: {summary['risk_level']}")
        
        return summary
    
    def _clean_thinking_process(self, text: str) -> str:
        """
        清理LLM输出中的思考过程（根据配置决定是否清理）
        
        移除<think>标签及其内容，以及其他可能的思考格式
        
        Args:
            text: LLM输出的原始文本
            
        Returns:
            清理后的文本（如果配置为显示思考过程，则返回原始文本）
        """
        # 如果配置为显示思考过程，则不清理
        if settings.SHOW_LLM_THINKING_PROCESS:
            logger.debug("配置为显示LLM思考过程，跳过清理")
            return text
        
        if not text:
            return text
        
        cleaned_text = text
        
        # 1. 移除<think>标签及其内容
        think_pattern = r'<think>[\s\S]*?</think>'
        cleaned_text = re.sub(think_pattern, '', cleaned_text, flags=re.DOTALL)
        
        # 2. 移除其他可能的思考标记
        # 例如：以思考开头的段落、特定的注释等
        thinking_markers = [
            r'^[\s]*思考[：:].*$',
            r'^[\s]*我需要.*$',
            r'^[\s]*好的.*$',
            r'^[\s]*接下来.*$',
            r'^[\s]*让我.*$',
            r'^[\s]*首先.*$',
            r'^[\s]*然后.*$',
            r'^[\s]*现在.*$'
        ]
        
        for marker in thinking_markers:
            cleaned_text = re.sub(marker, '', cleaned_text, flags=re.MULTILINE)
        
        # 3. 移除多余的空行
        cleaned_text = re.sub(r'\n\s*\n\s*\n', '\n\n', cleaned_text)
        
        # 4. 清理首尾空白
        cleaned_text = cleaned_text.strip()
        
        return cleaned_text
    
    def _extract_url_mappings(self, original_text: str, desensitized_text: str) -> Dict[str, str]:
        """
        提取URL路径段的映射关系
        
        Args:
            original_text: 原始文本
            desensitized_text: 脱敏后的文本
            
        Returns:
            Dict[str, str]: URL路径段映射关系
        """
        mappings = {}
        
        try:
            # 提取原始文本和脱敏文本中的URL
            # 改进的URL正则表达式，匹配更多格式
            # 支持中文冒号、英文冒号、空格等不同格式
            url_with_prefix_pattern = r'(?:(?:漏洞URL|URL|链接|网址)[：:](?:\s*|\s*`*)|(?:^|\s))(https?://[\w\-._~:/?#\[\]@!$&\'()*+,;=.]+)'
            
            # 提取原始URL
            original_matches = re.findall(url_with_prefix_pattern, original_text)
            original_urls = [match for match in original_matches]
            
            # 提取脱敏URL
            desensitized_matches = re.findall(url_with_prefix_pattern, desensitized_text)
            desensitized_urls = [match for match in desensitized_matches]
            
            # 假设URL是按顺序对应的
            min_count = min(len(original_urls), len(desensitized_urls))
            
            for i in range(min_count):
                original_url = original_urls[i]
                desensitized_url = desensitized_urls[i]
                
                # 提取路径段
                original_segments = self.url_desensitization_service.extract_path_segments(original_url)
                desensitized_segments = self.url_desensitization_service.extract_path_segments(desensitized_url)
                
                # 建立映射关系
                min_segments = min(len(original_segments), len(desensitized_segments))
                for j in range(min_segments):
                    original_segment = original_segments[j]
                    desensitized_segment = desensitized_segments[j]
                    
                    # 只有当路径段发生变化时才记录映射
                    if original_segment != desensitized_segment:
                        # 检查是否已存在映射
                        existing_map = self.url_desensitization_service.get_map(original_segment)
                        if not existing_map:
                            mappings[original_segment] = desensitized_segment
            
        except Exception as e:
            logger.error(f"提取URL映射失败: {e}")
        
        return mappings
