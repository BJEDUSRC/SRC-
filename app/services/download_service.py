# -*- coding: utf-8 -*-
"""
文档下载服务

提供单文件下载、批量下载、ZIP打包等功能。
"""

import zipfile
import tempfile
import os
import shutil
from pathlib import Path
from typing import Optional, List, Union
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session
import logging

from app.models.document import Document, DocumentImage, DownloadLog, DownloadType
from app.config import settings

logger = logging.getLogger(__name__)


class DownloadService:
    """
    文档下载服务
    
    提供以下功能：
    - 单文件下载（MD文件，可选包含图片）
    - 批量下载（多个文档打包为ZIP）
    - 下载记录管理
    """
    
    def __init__(self, db: Session):
        """
        初始化下载服务
        
        Args:
            db: 数据库会话
        """
        self.db = db
        self.converted_dir = Path(settings.CONVERTED_DIR)
        self.converted_dir.mkdir(parents=True, exist_ok=True)
    
    def download_single(
        self,
        doc_id: str,
        include_images: bool = True
    ) -> Optional[Union[FileResponse, StreamingResponse]]:
        """
        下载单个文档
        
        如果包含图片，返回ZIP文件；否则返回MD文件。
        
        Args:
            doc_id: 文档ID
            include_images: 是否包含图片
            
        Returns:
            FileResponse: 文件响应对象，文档不存在返回None
        """
        try:
            document = self.db.query(Document).filter(Document.id == doc_id).first()
            if not document:
                logger.warning(f"文档不存在: {doc_id}")
                return None
            
            # file_path 可能是绝对路径或相对路径
            file_path_str = document.file_path
            md_file_path = Path(file_path_str)
            
            # 检查是否是绝对路径（Windows路径以盘符开头，Unix路径以/开头）
            if not md_file_path.is_absolute() and not (len(file_path_str) > 1 and file_path_str[1] == ':'):
                # 如果是相对路径，则相对于 converted_dir
                md_file_path = self.converted_dir / md_file_path
            
            logger.info(f"尝试访问文件: {md_file_path} (原始路径: {file_path_str}, 是否为绝对路径: {md_file_path.is_absolute()})")
            
            if not md_file_path.exists():
                # 尝试其他可能的路径
                alt_paths = [
                    self.converted_dir / file_path_str,
                    Path(file_path_str),
                    self.converted_dir / document.id / document.filename
                ]
                logger.error(f"MD文件不存在: {md_file_path}")
                for alt_path in alt_paths:
                    if alt_path.exists():
                        logger.info(f"找到替代路径: {alt_path}")
                        md_file_path = alt_path
                        break
                else:
                    logger.error(f"所有路径都不存在。尝试的路径: {[str(p) for p in [md_file_path] + alt_paths]}")
                    return None
            
            # 如果不包含图片或没有图片，直接返回MD文件
            if not include_images or document.images_count == 0:
                self._log_download(doc_id, DownloadType.SINGLE, include_images)
                return FileResponse(
                    path=str(md_file_path),
                    filename=document.filename,
                    media_type='text/markdown; charset=utf-8'
                )
            
            # 包含图片，创建ZIP文件
            return self._create_single_zip(document, md_file_path)
            
        except Exception as e:
            logger.error(f"下载单个文档失败: {e}", exc_info=True)
            raise
    
    def _create_single_zip(
        self,
        document: Document,
        md_file_path: Path
    ) -> FileResponse:
        """
        为单个文档创建ZIP文件（包含MD和图片）
        
        Args:
            document: 文档对象
            md_file_path: MD文件路径
            
        Returns:
            FileResponse: ZIP文件响应
        """
        temp_dir = None
        try:
            # 创建临时目录
            temp_dir = tempfile.mkdtemp()
            zip_filename = f"{Path(document.filename).stem}.zip"
            zip_path = Path(temp_dir) / zip_filename
            
            # 创建ZIP文件（使用UTF-8编码支持中文文件名）
            # Python 3.11+ 支持 encoding 参数，旧版本需要手动处理
            try:
                # 尝试使用 encoding 参数（Python 3.11+）
                zf = zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED, compresslevel=6)
                # Python 3.11+ 自动处理UTF-8编码
            except TypeError:
                # 旧版本Python，使用默认方式
                zf = zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED)
            
            try:
                # 添加MD文件（直接使用write方法，让zipfile自动处理UTF-8）
                # Python 3默认使用UTF-8编码文件名
                with open(md_file_path, 'rb') as f:
                    md_content = f.read()
                # 使用write方法而不是writestr，这样zipfile会自动处理编码
                zf.writestr(document.filename, md_content)
                
                # 添加图片文件
                images = document.images.all() if hasattr(document.images, 'all') else list(document.images)
                for img in images:
                    # img.file_path 可能是绝对路径或相对路径
                    img_path = Path(img.file_path)
                    if not img_path.is_absolute():
                        img_path = self.converted_dir / img_path
                    
                    if img_path.exists():
                        # 保持目录结构：images/{doc_id}/{filename}
                        arcname = img.file_path
                        # 直接使用writestr，让zipfile自动处理UTF-8
                        with open(img_path, 'rb') as f:
                            zf.writestr(arcname, f.read())
                        logger.debug(f"添加图片到ZIP: {arcname}")
            finally:
                zf.close()
            
            # 记录下载日志
            self._log_download(document.id, DownloadType.SINGLE, True)
            
            logger.info(f"创建ZIP文件成功: {zip_path}")
            
            # 使用StreamingResponse以便在响应后清理临时文件
            def generate():
                try:
                    with open(zip_path, 'rb') as f:
                        while True:
                            chunk = f.read(8192)  # 8KB chunks
                            if not chunk:
                                break
                            yield chunk
                finally:
                    # 清理临时目录
                    if temp_dir and os.path.exists(temp_dir):
                        shutil.rmtree(temp_dir, ignore_errors=True)
                        logger.debug(f"已清理临时目录: {temp_dir}")
            
            # 使用 URL 编码处理中文文件名
            from urllib.parse import quote
            encoded_filename = quote(zip_filename)
            return StreamingResponse(
                generate(),
                media_type='application/zip',
                headers={
                    "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"
                }
            )
            
        except Exception as e:
            # 清理临时目录
            if temp_dir and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)
            logger.error(f"创建ZIP文件失败: {e}", exc_info=True)
            raise
    
    async def download_batch(
        self,
        doc_ids: List[str],
        include_images: bool = True
    ) -> Optional[StreamingResponse]:
        """
        批量下载文档
        
        将多个文档打包为ZIP文件。
        
        Args:
            doc_ids: 文档ID列表
            include_images: 是否包含图片
            
        Returns:
            StreamingResponse: ZIP文件流，文档不存在返回None
        """
        temp_dir = None
        try:
            # 查询文档
            documents = self.db.query(Document).filter(Document.id.in_(doc_ids)).all()
            if not documents:
                logger.warning(f"没有找到文档: {doc_ids}")
                return None
            
            # 创建临时目录
            temp_dir = tempfile.mkdtemp()
            zip_filename = "src_documents_batch.zip"
            zip_path = Path(temp_dir) / zip_filename
            
            # 创建ZIP文件（使用UTF-8编码支持中文文件名）
            try:
                zf = zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED, compresslevel=6)
            except TypeError:
                zf = zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED)
            
            added_files = 0  # 记录成功添加的文件数
            
            try:
                for doc in documents:
                    # file_path 可能是绝对路径或相对路径
                    file_path_str = doc.file_path
                    md_file_path = Path(file_path_str)
                    
                    # 检查是否是绝对路径
                    if not md_file_path.is_absolute() and not (len(file_path_str) > 1 and file_path_str[1] == ':'):
                        md_file_path = self.converted_dir / md_file_path
                    
                    logger.info(f"批量下载 - 处理文档: {doc.id}, 文件路径: {md_file_path}")
                    
                    if not md_file_path.exists():
                        logger.error(f"MD文件不存在，跳过: {md_file_path} (原始路径: {file_path_str})")
                        # 尝试其他可能的路径
                        alt_paths = [
                            self.converted_dir / file_path_str,
                            Path(file_path_str),
                            self.converted_dir / doc.id / doc.filename
                        ]
                        for alt_path in alt_paths:
                            if alt_path.exists():
                                logger.info(f"找到替代路径: {alt_path}")
                                md_file_path = alt_path
                                break
                        else:
                            logger.error(f"所有路径都不存在，跳过该文档")
                            continue
                    
                    # 为每个文档创建子目录
                    doc_dir = Path(doc.id)
                    
                    # 添加MD文件（直接使用writestr）
                    md_arcname = str(doc_dir / doc.filename)
                    with open(md_file_path, 'rb') as f:
                        md_content = f.read()
                        zf.writestr(md_arcname, md_content)
                        added_files += 1
                        logger.info(f"已添加MD文件到ZIP: {md_arcname} ({len(md_content)} bytes)")
                    
                    # 添加图片文件（如果包含）
                    if include_images and doc.images_count > 0:
                        images = doc.images.all() if hasattr(doc.images, 'all') else list(doc.images)
                        for img in images:
                            # img.file_path 可能是绝对路径或相对路径
                            img_path = Path(img.file_path)
                            if not img_path.is_absolute():
                                img_path = self.converted_dir / img_path
                            
                            if img_path.exists():
                                # 保持相对路径结构
                                arcname = str(doc_dir / img.file_path)
                                # 直接使用writestr
                                with open(img_path, 'rb') as f:
                                    img_content = f.read()
                                    zf.writestr(arcname, img_content)
                                    added_files += 1
                                    logger.debug(f"添加图片到ZIP: {arcname} ({len(img_content)} bytes)")
                            else:
                                logger.warning(f"图片文件不存在，跳过: {img_path}")
            finally:
                zf.close()
            
            # 检查是否有文件被添加
            if added_files == 0:
                logger.error(f"批量下载失败: 没有文件被添加到ZIP中")
                if temp_dir and os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir, ignore_errors=True)
                return None
            
            # 记录下载日志（为每个文档记录）
            for doc in documents:
                self._log_download(doc.id, DownloadType.BATCH, include_images)
            
            logger.info(f"创建批量ZIP文件成功: {zip_path}, 包含 {len(documents)} 个文档, {added_files} 个文件")
            
            # 读取ZIP文件内容
            def generate():
                try:
                    with open(zip_path, 'rb') as f:
                        while True:
                            chunk = f.read(8192)  # 8KB chunks
                            if not chunk:
                                break
                            yield chunk
                finally:
                    # 清理临时目录
                    if temp_dir and os.path.exists(temp_dir):
                        shutil.rmtree(temp_dir, ignore_errors=True)
            
            # 使用 URL 编码处理文件名（批量下载文件名通常是英文，但为了一致性也编码）
            from urllib.parse import quote
            encoded_filename = quote(zip_filename)
            return StreamingResponse(
                generate(),
                media_type='application/zip',
                headers={
                    "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"
                }
            )
            
        except Exception as e:
            # 清理临时目录
            if temp_dir and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)
            logger.error(f"批量下载失败: {e}", exc_info=True)
            raise
    
    def _log_download(
        self,
        doc_id: str,
        download_type: DownloadType,
        include_images: bool
    ) -> None:
        """
        记录下载日志
        
        Args:
            doc_id: 文档ID
            download_type: 下载类型
            include_images: 是否包含图片
        """
        try:
            download_log = DownloadLog(
                document_id=doc_id,
                download_type=download_type,
                include_images=include_images
            )
            self.db.add(download_log)
            self.db.commit()
            logger.debug(f"记录下载日志: doc_id={doc_id}, type={download_type}, images={include_images}")
        except Exception as e:
            self.db.rollback()
            logger.warning(f"记录下载日志失败: {e}")
    
    
    def get_download_stats(self, doc_id: str) -> dict:
        """
        获取文档下载统计
        
        Args:
            doc_id: 文档ID
            
        Returns:
            dict: 下载统计信息
        """
        try:
            total_downloads = self.db.query(DownloadLog).filter(
                DownloadLog.document_id == doc_id
            ).count()
            
            single_downloads = self.db.query(DownloadLog).filter(
                DownloadLog.document_id == doc_id,
                DownloadLog.download_type == DownloadType.SINGLE
            ).count()
            
            batch_downloads = self.db.query(DownloadLog).filter(
                DownloadLog.document_id == doc_id,
                DownloadLog.download_type == DownloadType.BATCH
            ).count()
            
            return {
                "total_downloads": total_downloads,
                "single_downloads": single_downloads,
                "batch_downloads": batch_downloads,
                "document_id": doc_id
            }
        except Exception as e:
            logger.error(f"获取下载统计失败: {e}", exc_info=True)
            return {
                "total_downloads": 0,
                "single_downloads": 0,
                "batch_downloads": 0,
                "document_id": doc_id
            }
