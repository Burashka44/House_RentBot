"""
Rate Limiting Middleware

Prevents spam and abuse by limiting requests per user.
"""
import logging
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Callable, Dict, Any, Awaitable, List

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, TelegramObject


class RateLimitMiddleware(BaseMiddleware):
    """
    Rate limiting middleware to prevent spam and abuse.
    
    Limits number of requests per user in a time window.
    """
    
    def __init__(
        self,
        rate: int = 10,
        per: int = 60,
        message: str = "⚠️ Слишком много запросов. Подождите немного."
    ):
        """
        Initialize rate limiter.
        
        Args:
            rate: Maximum number of requests
            per: Time window in seconds
            message: Message to show when rate limit exceeded
        """
        super().__init__()
        self.rate = rate
        self.per = per
        self.message = message
        self.requests: Dict[int, List[datetime]] = defaultdict(list)
        
        # Cache admin IDs to avoid repeated imports
        from bot.config import config
        self.admin_ids = set(config.OWNER_IDS + config.ADMIN_IDS)
        
        logging.info(f"Rate limiter initialized: {rate} requests per {per} seconds")
    
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        """
        Check rate limit before processing event.
        """
        # Get user ID
        user_id = None
        if isinstance(event, Message):
            user_id = event.from_user.id if event.from_user else None
        elif isinstance(event, CallbackQuery):
            user_id = event.from_user.id if event.from_user else None
        
        # Skip rate limiting if no user ID
        if not user_id:
            return await handler(event, data)
        
        # Skip rate limiting for admins/owners (cached)
        if user_id in self.admin_ids:
            return await handler(event, data)
        
        now = datetime.now()
        
        # Clean old requests
        self.requests[user_id] = [
            req_time for req_time in self.requests[user_id]
            if now - req_time < timedelta(seconds=self.per)
        ]
        
        # Check rate limit
        if len(self.requests[user_id]) >= self.rate:
            logging.warning(
                f"Rate limit exceeded for user {user_id}: "
                f"{len(self.requests[user_id])} requests in {self.per}s"
            )
            
            # Send rate limit message
            if isinstance(event, Message):
                await event.answer(self.message)
            elif isinstance(event, CallbackQuery):
                await event.answer(self.message, show_alert=True)
            
            return  # Don't process the request
        
        # Add request timestamp
        self.requests[user_id].append(now)
        
        # Process request
        return await handler(event, data)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get rate limiter statistics."""
        now = datetime.now()
        active_users = 0
        total_requests = 0
        
        for user_id, timestamps in self.requests.items():
            recent = [
                t for t in timestamps
                if now - t < timedelta(seconds=self.per)
            ]
            if recent:
                active_users += 1
                total_requests += len(recent)
        
        return {
            "active_users": active_users,
            "total_requests": total_requests,
            "rate_limit": f"{self.rate}/{self.per}s"
        }


class FileUploadRateLimiter(BaseMiddleware):
    """
    Stricter rate limiting for file uploads (receipts, photos).
    
    File uploads are more expensive (OCR, storage), so limit them more.
    """
    
    def __init__(
        self,
        rate: int = 3,
        per: int = 60,
        message: str = "⚠️ Слишком много файлов. Подождите минуту."
    ):
        super().__init__()
        self.rate = rate
        self.per = per
        self.message = message
        self.uploads: Dict[int, List[datetime]] = defaultdict(list)
        
        logging.info(f"File upload limiter initialized: {rate} uploads per {per} seconds")
    
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        """Check file upload rate limit."""
        # Only apply to messages with photos or documents
        if not isinstance(event, Message):
            return await handler(event, data)
        
        if not (event.photo or event.document):
            return await handler(event, data)
        
        user_id = event.from_user.id if event.from_user else None
        if not user_id:
            return await handler(event, data)
        
        # Skip for admins
        from bot.config import config
        if user_id in (config.OWNER_IDS + config.ADMIN_IDS):
            return await handler(event, data)
        
        now = datetime.now()
        
        # Clean old uploads
        self.uploads[user_id] = [
            upload_time for upload_time in self.uploads[user_id]
            if now - upload_time < timedelta(seconds=self.per)
        ]
        
        # Check limit
        if len(self.uploads[user_id]) >= self.rate:
            logging.warning(
                f"File upload rate limit exceeded for user {user_id}: "
                f"{len(self.uploads[user_id])} uploads in {self.per}s"
            )
            await event.answer(self.message)
            return
        
        # Add upload timestamp
        self.uploads[user_id].append(now)
        
        return await handler(event, data)
