"""
PDF转换服务模块

将PDF文档转换为Markdown格式，支持文本、表格和图片提取。
增强版：保留PDF的排版结构，包括标题层级、段落、列表、样式等。
"""

import fitz  # PyMuPDF
import pdfplumber
from typing import List, Dict, Optional, Tuple
import logging
from pathlib import Path
import re
from collections import defaultdict

from app.utils.logger import get_logger
from app.services.image_extractor import ImageExtractor

logger = get_logger(__name__)


class PDFConverter:
    """
    PDF转换服务类
    
    负责将PDF文档转换为Markdown格式，包括文本、表格和图片的提取。
    """
    
    def __init__(self, image_extractor: Optional[ImageExtractor] = None):
        """
        初始化PDF转换器
        
        Args:
            image_extractor: 图片提取器实例，如果为None则不提取图片
        """
        self.image_extractor = image_extractor
    
    def _analyze_font_sizes(self, blocks: List[Dict]) -> Dict[float, int]:
        """
        分析文本块中的字体大小分布，用于识别标题层级
        
        Args:
            blocks: 文本块列表
            
        Returns:
            字体大小到出现次数的映射
        """
        font_sizes = defaultdict(int)
        for block in blocks:
            if block.get("type") == 0:  # 文本块
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        size = span.get("size", 0)
                        if size > 0:
                            font_sizes[size] += 1
        return dict(font_sizes)
    
    def _determine_heading_level(self, font_size: float, font_sizes: Dict[float, int], 
                                 is_bold: bool = False) -> Optional[int]:
        """
        根据字体大小和样式确定标题层级
        
        Args:
            font_size: 字体大小
            font_sizes: 字体大小分布
            is_bold: 是否为粗体
            
        Returns:
            标题层级（1-6），如果不是标题则返回None
        """
        if not font_sizes:
            return None
        
        # 按字体大小排序
        sorted_sizes = sorted(font_sizes.keys(), reverse=True)
        
        # 如果字体大小明显大于正文（通常是最大的几个），且为粗体，可能是标题
        if len(sorted_sizes) > 0:
            max_size = sorted_sizes[0]
            # 如果字体大小大于等于最大字体的80%，且为粗体，可能是标题
            if font_size >= max_size * 0.8 and is_bold:
                # 根据字体大小在排序列表中的位置确定层级
                try:
                    index = sorted_sizes.index(font_size)
                    # 前3个最大字体对应h1-h3
                    if index == 0:
                        return 1
                    elif index == 1:
                        return 2
                    elif index == 2:
                        return 3
                    else:
                        return min(4, index + 1)
                except ValueError:
                    return None
        
        return None
    
    def _format_text_span(self, span: Dict) -> str:
        """
        格式化文本片段，保留样式（粗体、斜体）
        
        Args:
            span: 文本片段字典
            
        Returns:
            格式化后的文本
        """
        text = span.get("text", "").strip()
        if not text:
            return ""
        
        flags = span.get("flags", 0)
        is_bold = flags & 16  # 粗体标志
        is_italic = flags & 1  # 斜体标志
        
        # 应用样式
        if is_bold and is_italic:
            return f"***{text}***"
        elif is_bold:
            return f"**{text}**"
        elif is_italic:
            return f"*{text}*"
        else:
            return text
    
    def _merge_text_spans(self, spans: List[Dict]) -> str:
        """
        合并同一行的多个文本片段
        
        Args:
            spans: 文本片段列表
            
        Returns:
            合并后的文本
        """
        parts = []
        for span in spans:
            formatted = self._format_text_span(span)
            if formatted:
                parts.append(formatted)
        return "".join(parts)
    
    def _is_list_item(self, line: Dict, prev_line: Optional[Dict] = None) -> Tuple[bool, Optional[str]]:
        """
        判断是否为列表项
        
        Args:
            line: 当前行
            prev_line: 上一行（用于判断缩进）
            
        Returns:
            (是否为列表项, 列表标记)
        """
        text = ""
        for span in line.get("spans", []):
            text += span.get("text", "")
        
        text = text.strip()
        if not text:
            return False, None
        
        # 检查有序列表（数字开头，支持多种格式）
        ordered_match = re.match(r'^(\d+)[\.、）)\s]\s*(.+)', text)
        if ordered_match:
            return True, ordered_match.group(1) + "."
        
        # 检查无序列表（符号开头）
        unordered_match = re.match(r'^[•·▪▫○●■□◆◇★☆▲△▼▽]\s*(.+)', text)
        if unordered_match:
            return True, "-"
        
        # 检查中文列表标记（一、二、三...）
        chinese_num_match = re.match(r'^[一二三四五六七八九十]+[、．.]\s*(.+)', text)
        if chinese_num_match:
            return True, "-"
        
        # 检查带括号的中文列表标记
        if re.match(r'^[（(][一二三四五六七八九十]+[）)]\s*(.+)', text):
            return True, "-"
        
        # 检查字母列表（a. b. c. 或 A. B. C.）
        letter_match = re.match(r'^([a-zA-Z])[\.、）)]\s*(.+)', text)
        if letter_match:
            return True, letter_match.group(1).lower() + "."
        
        # 根据缩进判断（如果左边界明显大于上一行）
        if prev_line:
            current_bbox = line.get("bbox", [0, 0, 0, 0])
            prev_bbox = prev_line.get("bbox", [0, 0, 0, 0])
            # 如果当前行左边界比上一行大20以上，且文本较短（可能是列表项）
            if current_bbox[0] - prev_bbox[0] > 20 and len(text) < 100:
                return True, "-"
        
        return False, None
    
    def extract_text_with_fitz(self, pdf_path: str) -> str:
        """
        使用PyMuPDF提取PDF文本，增强版：保留排版结构
        
        Args:
            pdf_path: PDF文件路径
            
        Returns:
            提取的文本内容（Markdown格式，保留排版）
            
        Raises:
            FileNotFoundError: PDF文件不存在
            Exception: PDF处理失败
        """
        try:
            doc = fitz.open(pdf_path)
            text_parts = []
            
            logger.info(f"开始提取PDF文本（PyMuPDF增强版）: {pdf_path}")
            
            page_count = len(doc)
            
            # 第一遍：分析所有页面的字体大小分布
            all_blocks = []
            for page_num in range(page_count):
                page = doc[page_num]
                blocks = page.get_text("dict")
                all_blocks.extend(blocks.get("blocks", []))
            
            font_sizes = self._analyze_font_sizes(all_blocks)
            logger.debug(f"字体大小分布: {sorted(font_sizes.keys(), reverse=True)[:5]}")
            
            # 第二遍：逐页提取并格式化
            for page_num in range(page_count):
                page = doc[page_num]
                blocks = page.get_text("dict")
                
                page_content = []
                prev_line = None
                in_list = False
                list_indent = 0
                
                for block in blocks.get("blocks", []):
                    if block.get("type") == 0:  # 文本块
                        lines = block.get("lines", [])
                        
                        for line in lines:
                            spans = line.get("spans", [])
                            if not spans:
                                continue
                            
                            # 获取第一行的字体信息
                            first_span = spans[0]
                            font_size = first_span.get("size", 0)
                            flags = first_span.get("flags", 0)
                            is_bold = bool(flags & 16)
                            
                            # 合并文本
                            line_text = self._merge_text_spans(spans)
                            if not line_text.strip():
                                continue
                            
                            # 判断是否为标题
                            heading_level = self._determine_heading_level(
                                font_size, font_sizes, is_bold
                            )
                            
                            if heading_level:
                                # 如果是标题，结束当前列表
                                if in_list:
                                    page_content.append("")
                                    in_list = False
                                
                                # 添加标题
                                heading_prefix = "#" * heading_level
                                page_content.append(f"\n{heading_prefix} {line_text.strip()}\n")
                                prev_line = line
                                continue
                            
                            # 判断是否为列表项
                            is_list, list_marker = self._is_list_item(line, prev_line)
                            
                            if is_list:
                                if not in_list:
                                    page_content.append("")
                                    in_list = True
                                
                                # 添加列表项
                                if list_marker == "-":
                                    page_content.append(f"- {line_text.strip()}")
                                else:
                                    # 有序列表，提取数字
                                    match = re.match(r'^(\d+)[\.、）)]\s*(.+)', line_text)
                                    if match:
                                        num = match.group(1)
                                        content = match.group(2)
                                        page_content.append(f"{num}. {content.strip()}")
                                    else:
                                        page_content.append(f"- {line_text.strip()}")
                            else:
                                # 普通段落
                                if in_list:
                                    page_content.append("")
                                    in_list = False
                                
                                # 检查是否需要添加空行分隔段落
                                if page_content and page_content[-1].strip():
                                    # 如果上一行不是空行且不是标题，添加空行
                                    last_line = page_content[-1].strip()
                                    if not last_line.startswith("#"):
                                        page_content.append("")
                                
                                # 处理多行文本（保持原有换行）
                                page_content.append(line_text.strip())
                            
                            prev_line = line
                    
                    elif block.get("type") == 1:  # 图片块
                        # 图片会在后续处理中插入
                        pass
                
                # 合并页面内容
                if page_content:
                    page_text = "\n".join(page_content)
                    if page_text.strip():
                        # 直接添加内容，不添加页码标记
                        text_parts.append(page_text)
            
            result = "\n\n".join(text_parts)
            
            # 清理多余的空行（保留段落间的单个空行）
            result = re.sub(r'\n{3,}', '\n\n', result)
            
            doc.close()
            
            logger.info(f"PDF文本提取完成，共 {page_count} 页")
            
            return result
            
        except Exception as e:
            logger.error(f"PyMuPDF文本提取失败: {pdf_path}", exc_info=True)
            # 如果增强版失败，回退到简单版本
            logger.warning("增强版提取失败，使用简单版本回退")
            return self._extract_text_simple_fallback(pdf_path)
    
    def _extract_text_simple_fallback(self, pdf_path: str) -> str:
        """
        简单版本的文本提取（回退方案）
        
        Args:
            pdf_path: PDF文件路径
            
        Returns:
            提取的文本内容
        """
        try:
            doc = fitz.open(pdf_path)
            text_parts = []
            page_count = len(doc)
            
            for page_num in range(page_count):
                page = doc[page_num]
                text = page.get_text("text")
                
                if text.strip():
                    # 不添加页码标记
                    text_parts.append(text)
            
            result = "\n".join(text_parts)
            doc.close()
            return result
            
        except Exception as e:
            logger.error(f"简单版本文本提取也失败: {pdf_path}", exc_info=True)
            raise
    
    def extract_tables_with_pdfplumber(self, pdf_path: str) -> List[Dict]:
        """
        使用pdfplumber提取PDF中的表格
        
        Args:
            pdf_path: PDF文件路径
            
        Returns:
            表格列表，每个表格包含 {page, index, data}
        """
        tables = []
        
        try:
            logger.info(f"开始提取PDF表格（pdfplumber）: {pdf_path}")
            
            with pdfplumber.open(pdf_path) as pdf:
                for page_num, page in enumerate(pdf.pages, 1):
                    page_tables = page.extract_tables()
                    
                    if page_tables:
                        logger.debug(f"第 {page_num} 页发现 {len(page_tables)} 个表格")
                        
                        for table_index, table in enumerate(page_tables, 1):
                            if table:  # 确保表格不为空
                                tables.append({
                                    "page": page_num,
                                    "index": table_index,
                                    "data": table
                                })
            
            logger.info(f"PDF表格提取完成，共发现 {len(tables)} 个表格")
            return tables
            
        except Exception as e:
            logger.warning(f"pdfplumber表格提取失败: {pdf_path}, {e}")
            return []
    
    @staticmethod
    def table_to_markdown(table: List[List[str]]) -> str:
        """
        将表格数据转换为纯文本内容（不包含Markdown表格样式）
        
        Args:
            table: 二维表格数据
            
        Returns:
            表格内容的纯文本字符串（每行用空格分隔单元格）
        """
        if not table or len(table) < 1:
            return ""
        
        # 处理表格数据，替换None为空字符串
        cleaned_table = []
        for row in table:
            if not row:  # 跳过空行
                continue
            cleaned_row = [str(cell or "").strip() for cell in row]
            # 过滤掉完全空的行
            if any(cell for cell in cleaned_row):
                cleaned_table.append(cleaned_row)
        
        if not cleaned_table:
            return ""
        
        # 将表格内容转换为纯文本，每行用空格分隔单元格
        text_lines = []
        for row in cleaned_table:
            # 用空格连接非空单元格
            row_text = " ".join(cell for cell in row if cell.strip())
            if row_text.strip():
                text_lines.append(row_text)
        
        return "\n".join(text_lines)
    
    def convert_to_markdown(
        self, 
        pdf_path: str,
        doc_id: Optional[str] = None,
        extract_images: bool = True,
        extract_tables: bool = True
    ) -> Tuple[str, List[Dict]]:
        """
        将PDF转换为Markdown格式，增强版：保留排版结构并在正确位置插入表格和图片
        
        Args:
            pdf_path: PDF文件路径
            doc_id: 文档ID（用于图片提取）
            extract_images: 是否提取图片
            extract_tables: 是否提取表格
            
        Returns:
            (markdown_content, images_info) 元组
            - markdown_content: Markdown格式的文档内容
            - images_info: 提取的图片信息列表
            
        Raises:
            FileNotFoundError: PDF文件不存在
            Exception: 转换失败
        """
        logger.info(f"开始转换PDF到Markdown（增强版）: {pdf_path}")
        
        # 提取文本（增强版，保留排版）
        text_content = self.extract_text_with_fitz(pdf_path)
        
        # 提取图片信息（表格内容已包含在文本中，无需单独处理）
        images_info = []
        
        if extract_images and self.image_extractor and doc_id:
            try:
                images_info = self.image_extractor.extract_images(pdf_path, doc_id)
                logger.info(f"提取到 {len(images_info)} 张图片")
            except Exception as e:
                logger.error(f"图片提取失败: {e}", exc_info=True)
                # 图片提取失败不影响整体转换
        
        # 构建Markdown内容
        markdown_parts = [f"# {Path(pdf_path).stem}\n"]
        
        # 直接使用文本内容（已不包含页码标记）
        markdown_parts.append(text_content)
        
        # 不再单独添加表格内容，因为表格内容通常已经包含在文本提取中
        # 如果需要表格内容，它们已经在 text_content 中以文本形式存在
        
        # 在文档末尾添加所有图片
        if images_info:
            for img_info in images_info:
                img_ref = ImageExtractor.generate_md_image_ref(img_info)
                markdown_parts.append("\n\n" + img_ref)
        
        markdown_content = "\n".join(markdown_parts)
        
        # 最终清理：移除多余空行
        markdown_content = re.sub(r'\n{4,}', '\n\n\n', markdown_content)
        
        logger.info(
            f"PDF转换完成: 文本长度={len(markdown_content)}, "
            f"图片数={len(images_info)}"
        )
        
        return markdown_content, images_info
    
    def convert_and_save(
        self,
        pdf_path: str,
        output_path: str,
        doc_id: Optional[str] = None,
        extract_images: bool = True,
        extract_tables: bool = True
    ) -> Tuple[str, List[Dict]]:
        """
        转换PDF并保存为Markdown文件
        
        Args:
            pdf_path: PDF文件路径
            output_path: 输出Markdown文件路径
            doc_id: 文档ID
            extract_images: 是否提取图片
            extract_tables: 是否提取表格
            
        Returns:
            (markdown_content, images_info) 元组
            
        Raises:
            Exception: 转换或保存失败
        """
        markdown_content, images_info = self.convert_to_markdown(
            pdf_path=pdf_path,
            doc_id=doc_id,
            extract_images=extract_images,
            extract_tables=extract_tables
        )
        
        # 保存Markdown文件
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(markdown_content)
            
            logger.info(f"Markdown文件已保存: {output_path}")
            
        except Exception as e:
            logger.error(f"保存Markdown文件失败: {output_path}", exc_info=True)
            raise
        
        return markdown_content, images_info
