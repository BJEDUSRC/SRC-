# -*- coding: utf-8 -*-
"""
LangChain大模型服务模块 (适配 LangChain 1.2)

封装LangChain接口，支持多种大模型提供商（OpenAI、通义千问等）。
使用 LangChain 1.2 的新 API。
"""

from langchain_openai import ChatOpenAI
from langchain_community.chat_models import ChatTongyi
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.callbacks import CallbackManager
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from typing import Optional, List, Dict, Any
import logging
import os

from app.config import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)


class LLMService:
    """
    大模型服务类 (LangChain 1.2)
    
    封装LangChain的调用接口，支持多种LLM提供商，提供统一的调用方式。
    
    对于OpenAI兼容的模型：
    - 支持任何符合OpenAI接口的模型（如gpt-4, gpt-4o-mini, gpt-3.5-turbo等）
    - 使用环境变量方式配置，更灵活且兼容性更好
    - 优先使用配置中的LLM_API_KEY和LLM_API_BASE
    - 如果配置为空，自动从环境变量OPENAI_API_KEY和OPENAI_BASE_URL读取
    - 支持代理地址和自定义API端点
    
    配置方式（按优先级）：
    1. .env文件中的LLM_API_KEY和LLM_API_BASE
    2. 环境变量OPENAI_API_KEY和OPENAI_BASE_URL
    3. 默认值（仅API地址，API密钥必须配置）
    """
    
    def __init__(
        self,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        api_base: Optional[str] = None,
        temperature: float = 0.8,
        max_tokens: int = 4000
    ):
        """
        初始化LLM服务
        
        Args:
            provider: 提供商名称 (openai, qwen)，默认从配置读取
            model: 模型名称，支持任何符合OpenAI接口的模型（如gpt-4, gpt-4o-mini等），默认从配置读取
            api_key: API密钥，默认从配置读取。如果为空，将从环境变量OPENAI_API_KEY读取
            api_base: API基础URL，默认从配置读取。如果为空，将从环境变量OPENAI_BASE_URL读取
            temperature: 温度参数（0-1），越低越确定性
            max_tokens: 最大生成token数
            
        Note:
            OpenAI兼容模型的配置优先级：
            1. 传入的api_key和api_base参数
            2. 配置中的LLM_API_KEY和LLM_API_BASE
            3. 环境变量OPENAI_API_KEY和OPENAI_BASE_URL
            4. 默认值（仅API地址，API密钥必须配置）
        """
        self.provider = provider or settings.LLM_PROVIDER
        self.model = model or settings.LLM_MODEL
        self.api_key = api_key or settings.LLM_API_KEY
        self.api_base = api_base or settings.LLM_API_BASE
        self.temperature = temperature
        self.max_tokens = max_tokens
        
        self._llm = None
        
        logger.info(
            f"初始化LLM服务: provider={self.provider}, "
            f"model={self.model}, temperature={temperature}"
        )
    
    def get_llm(self):
        """
        获取LLM实例（懒加载）
        
        Returns:
            LangChain的LLM实例
            
        Raises:
            ValueError: 不支持的提供商
        """
        if self._llm is None:
            if self.provider == "openai":
                try:
                    # LangChain 1.2: 使用环境变量方式，支持任何符合OpenAI接口的模型
                    # 设置环境变量（ChatOpenAI会自动从环境变量读取）
                    # 优先使用配置中的值，如果没有则使用环境变量中已有的值
                    if self.api_key:
                        os.environ["OPENAI_API_KEY"] = self.api_key
                    elif not os.environ.get("OPENAI_API_KEY"):
                        raise ValueError("OPENAI_API_KEY未配置，请在.env文件中设置LLM_API_KEY或OPENAI_API_KEY")
                    
                    # 支持OPENAI_BASE_URL环境变量（兼容性更好）
                    if self.api_base:
                        os.environ["OPENAI_BASE_URL"] = self.api_base
                        # 同时设置OPENAI_API_BASE以兼容旧代码
                        os.environ["OPENAI_API_BASE"] = self.api_base
                    elif not os.environ.get("OPENAI_BASE_URL") and not os.environ.get("OPENAI_API_BASE"):
                        # 如果没有设置，使用默认值
                        default_base = "https://api.openai.com/v1"
                        os.environ["OPENAI_BASE_URL"] = default_base
                        logger.info(f"使用默认OpenAI API地址: {default_base}")
                    
                    # LangChain 1.2: 使用新的初始化方式
                    # ChatOpenAI 会自动从环境变量读取配置
                    self._llm = ChatOpenAI(
                        model=self.model,
                        temperature=self.temperature,
                        max_tokens=self.max_tokens if self.max_tokens else None
                    )
                    
                    base_url = os.environ.get("OPENAI_BASE_URL") or os.environ.get("OPENAI_API_BASE", "默认")
                    logger.info(
                        f"已初始化OpenAI兼容模型: {self.model}, "
                        f"base_url={base_url}"
                    )
                    
                except Exception as e:
                    logger.error(f"OpenAI模型初始化失败: {e}", exc_info=True)
                    raise ValueError(f"无法初始化OpenAI模型: {e}")
                
            elif self.provider == "qwen":
                self._llm = ChatTongyi(
                    model=self.model,
                    dashscope_api_key=self.api_key,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens
                )
                logger.info(f"已初始化通义千问模型: {self.model}")
                
            else:
                raise ValueError(f"不支持的LLM提供商: {self.provider}")
        
        return self._llm
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=1, max=10),
        retry=retry_if_exception_type((TimeoutError, ConnectionError)),
        reraise=True
    )
    async def ainvoke(
        self,
        prompt: str,
        system_message: Optional[str] = None
    ) -> str:
        """
        异步调用LLM（带重试机制）
        
        Args:
            prompt: 用户提示词
            system_message: 系统提示词（可选）
            
        Returns:
            LLM的响应文本
            
        Raises:
            Exception: LLM调用失败
        """
        try:
            llm = self.get_llm()
            
            # LangChain 1.2: 使用新的消息格式
            messages = []
            if system_message:
                messages.append(SystemMessage(content=system_message))
            messages.append(HumanMessage(content=prompt))
            
            # 调用LLM
            response = await llm.ainvoke(messages)
            
            # LangChain 1.2: 响应是AIMessage对象，content属性包含文本
            result = response.content if hasattr(response, 'content') else str(response)
            
            logger.info(f"LLM调用成功: model={self.model}")
            
            return result
                
        except Exception as e:
            logger.error(f"LLM调用失败: {e}", exc_info=True)
            raise
    
    def invoke(
        self,
        prompt: str,
        system_message: Optional[str] = None
    ) -> str:
        """
        同步调用LLM
        
        Args:
            prompt: 用户提示词
            system_message: 系统提示词（可选）
            
        Returns:
            LLM的响应文本
        """
        try:
            llm = self.get_llm()
            
            # LangChain 1.2: 使用新的消息格式
            messages = []
            if system_message:
                messages.append(SystemMessage(content=system_message))
            messages.append(HumanMessage(content=prompt))
            
            # 调用LLM
            response = llm.invoke(messages)
            
            # LangChain 1.2: 响应是AIMessage对象，content属性包含文本
            result = response.content if hasattr(response, 'content') else str(response)
            
            logger.info(f"LLM调用成功: model={self.model}")
            
            return result
                
        except Exception as e:
            logger.error(f"LLM调用失败: {e}", exc_info=True)
            raise
    
    async def batch_ainvoke(
        self,
        prompts: List[str],
        system_message: Optional[str] = None
    ) -> List[str]:
        """
        批量异步调用LLM
        
        Args:
            prompts: 提示词列表
            system_message: 系统提示词
            
        Returns:
            响应文本列表
        """
        results = []
        
        for i, prompt in enumerate(prompts, 1):
            try:
                logger.info(f"处理第 {i}/{len(prompts)} 个请求")
                result = await self.ainvoke(prompt, system_message)
                results.append(result)
            except Exception as e:
                logger.error(f"批量请求第 {i} 个失败: {e}")
                results.append(f"[错误: {str(e)}]")
        
        return results
    
    def split_text_by_tokens(
        self,
        text: str,
        max_tokens: int = 3000,
        overlap: int = 200
    ) -> List[str]:
        """
        按token数分割长文本
        
        Args:
            text: 原始文本
            max_tokens: 每块最大token数（估算为字符数）
            overlap: 块之间的重叠字符数
            
        Returns:
            文本块列表
            
        Note:
            这是简化实现，实际token数计算需要使用tokenizer
        """
        # LangChain 1.2: 文本分割器从 langchain_text_splitters 导入
        try:
            from langchain_text_splitters import RecursiveCharacterTextSplitter
        except ImportError:
            # 兼容旧版本
            from langchain.text_splitter import RecursiveCharacterTextSplitter
        
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=max_tokens,
            chunk_overlap=overlap,
            length_function=len,
            separators=["\n\n", "\n", "。", ".", " ", ""]
        )
        
        chunks = splitter.split_text(text)
        logger.info(f"文本已分割为 {len(chunks)} 块")
        
        return chunks
    
    async def process_long_text(
        self,
        text: str,
        system_message: str,
        max_tokens: int = 3000
    ) -> List[str]:
        """
        处理长文本（自动分块）
        
        Args:
            text: 长文本
            system_message: 系统提示词
            max_tokens: 每块最大token数
            
        Returns:
            处理结果列表（每块的结果）
        """
        # 分割文本
        chunks = self.split_text_by_tokens(text, max_tokens)
        
        # 批量处理
        results = await self.batch_ainvoke(chunks, system_message)
        
        return results
    
    def get_token_count(self, text: str) -> int:
        """
        估算文本的token数量
        
        Args:
            text: 输入文本
            
        Returns:
            估算的token数量
            
        Note:
            简化实现，实际应使用对应模型的tokenizer
        """
        # 中文字符通常1个字=1-2个token
        # 英文单词通常1个单词=1-2个token
        # 这里简单估算：中文*1.5，英文*0.3
        
        chinese_chars = sum(1 for char in text if '\u4e00' <= char <= '\u9fff')
        total_chars = len(text)
        english_chars = total_chars - chinese_chars
        
        estimated_tokens = int(chinese_chars * 1.5 + english_chars * 0.3)
        
        return estimated_tokens
