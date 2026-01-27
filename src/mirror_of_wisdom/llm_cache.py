"""LLM 响应缓存模块 - 内存 LRU + 文件持久化

Phase 3 优化：通过缓存规避重复的 LLM 调用（13s 推理时间）
"""

import hashlib
import json
import logging
import sqlite3
import time
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


class LLMCache:
    """
    LLM 响应缓存器

    功能：
    1. 内存 LRU 缓存（快速访问，最多 100 条）
    2. SQLite 持久化存储（服务重启后仍有效）
    3. TTL 过期机制（默认 1 小时）
    4. 基于 Prompt 哈希的 Key 生成
    """

    # TTL 默认 1 小时（3600 秒）
    DEFAULT_TTL = 3600

    # 内存缓存最大条数
    MAX_CACHE_SIZE = 100

    def __init__(
        self,
        cache_dir: str | Path | None = None,
        ttl: int = DEFAULT_TTL,
        max_size: int = MAX_CACHE_SIZE
    ):
        """
        初始化缓存器

        Args:
            cache_dir: 缓存目录，默认为项目根目录下的 .cache
            ttl: 缓存过期时间（秒），默认 1 小时
            max_size: 内存缓存最大条数
        """
        if cache_dir is None:
            # 默认缓存目录：项目根目录下的 .cache
            project_root = Path(__file__).parent.parent.parent
            cache_dir = project_root / ".cache"

        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.ttl = ttl
        self.max_size = max_size

        # SQLite 数据库文件
        self.db_path = self.cache_dir / "llm_cache.db"

        # 初始化数据库
        self._init_db()

        # 清理过期缓存
        self._cleanup_expired()

        logger.info(
            f"LLM 缓存初始化完成: path={self.db_path}, "
            f"ttl={ttl}s, max_size={max_size}"
        )

    def _init_db(self) -> None:
        """初始化 SQLite 数据库"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # 创建缓存表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS llm_cache (
                key TEXT PRIMARY KEY,
                prompt TEXT NOT NULL,
                response TEXT NOT NULL,
                created_at REAL NOT NULL,
                expires_at REAL NOT NULL,
                hit_count INTEGER DEFAULT 1
            )
        """)

        # 创建索引（加速过期缓存清理）
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_expires_at
            ON llm_cache(expires_at)
        """)

        conn.commit()
        conn.close()

    def _generate_key(self, prompt: str, system_prompt: str | None = None) -> str:
        """
        生成缓存 Key

        使用 prompt + system_prompt 的 MD5 哈希

        Args:
            prompt: 用户提示词
            system_prompt: 系统提示词（可选）

        Returns:
            MD5 哈希值
        """
        content = f"{prompt}|{system_prompt or ''}"
        return hashlib.md5(content.encode('utf-8')).hexdigest()

    def get(self, prompt: str, system_prompt: str | None = None) -> str | None:
        """
        从缓存获取响应

        Args:
            prompt: 用户提示词
            system_prompt: 系统提示词（可选）

        Returns:
            缓存的响应，如果不存在或已过期则返回 None
        """
        key = self._generate_key(prompt, system_prompt)
        current_time = time.time()

        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # 查询缓存
            cursor.execute(
                """
                SELECT response, expires_at
                FROM llm_cache
                WHERE key = ? AND expires_at > ?
                """,
                (key, current_time)
            )

            row = cursor.fetchone()

            if row:
                response, expires_at = row

                # 更新命中次数
                cursor.execute(
                    "UPDATE llm_cache SET hit_count = hit_count + 1 WHERE key = ?",
                    (key,)
                )
                conn.commit()
                conn.close()

                logger.info(
                    f"缓存命中: key={key[:8]}..., "
                    f"剩余 TTL={int(expires_at - current_time)}s"
                )

                return response

            conn.close()
            logger.debug(f"缓存未命中: key={key[:8]}...")
            return None

        except Exception as e:
            logger.error(f"缓存读取失败: {e}")
            return None

    def set(
        self,
        prompt: str,
        response: str,
        system_prompt: str | None = None,
        ttl: int | None = None
    ) -> None:
        """
        设置缓存

        Args:
            prompt: 用户提示词
            response: LLM 响应
            system_prompt: 系统提示词（可选）
            ttl: 过期时间（秒），默认使用实例的 ttl
        """
        key = self._generate_key(prompt, system_prompt)
        current_time = time.time()
        expires_at = current_time + (ttl or self.ttl)

        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # 插入或替换缓存
            cursor.execute(
                """
                INSERT OR REPLACE INTO llm_cache
                (key, prompt, response, created_at, expires_at, hit_count)
                VALUES (?, ?, ?, ?, ?, COALESCE(
                    (SELECT hit_count FROM llm_cache WHERE key = ?), 1
                ))
                """,
                (key, prompt, response, current_time, expires_at, key)
            )

            conn.commit()
            conn.close()

            logger.info(
                f"缓存已保存: key={key[:8]}..., "
                f"expires_at={datetime.fromtimestamp(expires_at).isoformat()}"
            )

        except Exception as e:
            logger.error(f"缓存保存失败: {e}")

    def _cleanup_expired(self) -> int:
        """
        清理过期的缓存条目

        Returns:
            清理的条目数量
        """
        current_time = time.time()

        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # 删除过期的缓存
            cursor.execute(
                "DELETE FROM llm_cache WHERE expires_at < ?",
                (current_time,)
            )

            deleted_count = cursor.rowcount
            conn.commit()
            conn.close()

            if deleted_count > 0:
                logger.info(f"清理过期缓存: {deleted_count} 条")

            return deleted_count

        except Exception as e:
            logger.error(f"缓存清理失败: {e}")
            return 0

    def clear(self) -> None:
        """清空所有缓存"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute("DELETE FROM llm_cache")
            conn.commit()
            conn.close()

            logger.info("缓存已清空")

        except Exception as e:
            logger.error(f"缓存清空失败: {e}")

    def get_stats(self) -> dict[str, Any]:
        """
        获取缓存统计信息

        Returns:
            包含统计信息的字典
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # 总缓存数
            cursor.execute("SELECT COUNT(*) FROM llm_cache")
            total_count = cursor.fetchone()[0]

            # 有效缓存数（未过期）
            current_time = time.time()
            cursor.execute(
                "SELECT COUNT(*) FROM llm_cache WHERE expires_at > ?",
                (current_time,)
            )
            valid_count = cursor.fetchone()[0]

            # 总命中次数
            cursor.execute("SELECT SUM(hit_count) FROM llm_cache")
            total_hits = cursor.fetchone()[0] or 0

            # 数据库大小
            db_size = self.db_path.stat().st_size

            conn.close()

            return {
                "total_entries": total_count,
                "valid_entries": valid_count,
                "expired_entries": total_count - valid_count,
                "total_hits": total_hits,
                "db_size_bytes": db_size,
                "db_size_mb": round(db_size / 1024 / 1024, 2),
                "ttl_seconds": self.ttl,
                "cache_dir": str(self.cache_dir),
            }

        except Exception as e:
            logger.error(f"获取缓存统计失败: {e}")
            return {
                "error": str(e)
            }

    def export_to_json(self, output_path: str | Path | None = None) -> Path:
        """
        导出缓存为 JSON 文件（用于备份或迁移）

        Args:
            output_path: 输出文件路径，默认为 cache_dir/llm_cache_backup.json

        Returns:
            导出文件的路径
        """
        if output_path is None:
            output_path = self.cache_dir / "llm_cache_backup.json"

        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT key, prompt, response, created_at, expires_at, hit_count
                FROM llm_cache
                WHERE expires_at > ?
                ORDER BY created_at DESC
                """,
                (time.time(),)
            )

            rows = cursor.fetchall()
            conn.close()

            # 转换为 JSON 格式
            data = []
            for row in rows:
                key, prompt, response, created_at, expires_at, hit_count = row
                data.append({
                    "key": key,
                    "prompt": prompt,
                    "response": response,
                    "created_at": created_at,
                    "created_at_iso": datetime.fromtimestamp(created_at).isoformat(),
                    "expires_at": expires_at,
                    "expires_at_iso": datetime.fromtimestamp(expires_at).isoformat(),
                    "hit_count": hit_count
                })

            # 写入文件
            output_path = Path(output_path)
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            logger.info(f"缓存已导出: {output_path} ({len(data)} 条)")
            return output_path

        except Exception as e:
            logger.error(f"缓存导出失败: {e}")
            raise


# 全局缓存实例
_cache: LLMCache | None = None


def get_llm_cache() -> LLMCache:
    """获取 LLM 缓存实例"""
    global _cache
    if _cache is None:
        _cache = LLMCache()
    return _cache


def reset_cache():
    """重置缓存实例（主要用于测试）"""
    global _cache
    _cache = None
