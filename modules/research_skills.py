import logging
import json
import time
import re
import os
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
import threading
import queue

logger = logging.getLogger("ResearchSkills")

import random
class ResearchSkills:
    """研究技能模块 - 信息搜集、竞品调研、比价购物、抢票等功能"""

    def __init__(self, config_manager=None):
        self.config_manager = config_manager
        self.research_history = []  # 研究历史记录
        self.price_watch_list = {}  # 价格监控列表
        self.ticket_monitors = {}   # 票务监控器
        self.load_research_data()

    def load_research_data(self):
        """加载研究数据"""
        data_dir = Path(__file__).parent.parent / "knowledge_base" / "data"
        data_dir.mkdir(parents=True, exist_ok=True)

        # 加载价格监控列表
        price_file = data_dir / "price_watch_list.json"
        if price_file.exists():
            try:
                with open(price_file, 'r', encoding='utf-8') as f:
                    self.price_watch_list = json.load(f)
                logger.info(f"已加载 {len(self.price_watch_list)} 个价格监控项")
            except Exception as e:
                logger.error(f"加载价格监控列表失败: {e}")

        # 加载研究历史
        history_file = data_dir / "research_history.json"
        if history_file.exists():
            try:
                with open(history_file, 'r', encoding='utf-8') as f:
                    self.research_history = json.load(f)
                logger.info(f"已加载 {len(self.research_history)} 条研究历史")
            except Exception as e:
                logger.error(f"加载研究历史失败: {e}")

    def save_research_data(self):
        """保存研究数据"""
        data_dir = Path(__file__).parent.parent / "knowledge_base" / "data"
        data_dir.mkdir(parents=True, exist_ok=True)

        # 保存价格监控列表
        price_file = data_dir / "price_watch_list.json"
        try:
            with open(price_file, 'w', encoding='utf-8') as f:
                json.dump(self.price_watch_list, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存价格监控列表失败: {e}")

        # 保存研究历史
        history_file = data_dir / "research_history.json"
        try:
            with open(history_file, 'w', encoding='utf-8') as f:
                json.dump(self.research_history, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存研究历史失败: {e}")

    def competitor_research(self, company_name: str, timeframe_days: int = 30,
                          product_keywords: List[str] = None) -> Dict[str, Any]:
        """竞品调研

        Args:
            company_name: 公司/品牌名称
            timeframe_days: 时间范围（天）
            product_keywords: 产品关键词列表

        Returns:
            包含竞品信息的字典
        """
        logger.info(f"开始竞品调研：{company_name}，时间范围：{timeframe_days}天")

        try:
            # 实际应该使用网络爬虫或API获取数据
            # 这里使用模拟数据演示

            # 模拟网络搜索
            search_results = self._simulate_web_search(company_name, product_keywords)

            # 提取产品信息
            products = self._extract_product_info(search_results)

            # 整理为表格格式
            table_data = self._format_as_table(products, timeframe_days)

            # 保存到研究历史
            research_record = {
                "company": company_name,
                "timeframe": timeframe_days,
                "date": datetime.now().isoformat(),
                "product_count": len(products),
                "table_data": table_data
            }
            self.research_history.append(research_record)
            self.save_research_data()

            return {
                "success": True,
                "company": company_name,
                "products_found": len(products),
                "table_data": table_data,
                "summary": self._generate_summary(products)
            }

        except Exception as e:
            logger.error(f"竞品调研失败: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    def _simulate_web_search(self, company_name: str, keywords: List[str] = None) -> List[Dict]:
        """模拟网页搜索（实际应使用selenium或requests）"""
        # 模拟延迟
        time.sleep(1)

        # 模拟搜索结果
        mock_results = [
            {
                "title": f"{company_name}发布全新AI产品",
                "source": "科技新闻",
                "date": (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d"),
                "content": f"{company_name}近日发布了全新的AI助手产品，定价为1999元，支持自然语言交互和自动化办公。",
                "url": "https://example.com/news/1"
            },
            {
                "title": f"{company_name}与友商合作推出企业解决方案",
                "source": "商业新闻",
                "date": (datetime.now() - timedelta(days=15)).strftime("%Y-%m-%d"),
                "content": f"{company_name}宣布与合作伙伴推出针对中小企业的AI解决方案，起售价为2999元/年。",
                "url": "https://example.com/news/2"
            },
            {
                "title": f"{company_name}获得新一轮融资",
                "source": "财经新闻",
                "date": (datetime.now() - timedelta(days=25)).strftime("%Y-%m-%d"),
                "content": f"{company_name}完成5000万美元B轮融资，估值达到5亿美元。",
                "url": "https://example.com/news/3"
            }
        ]

        if keywords:
            # 模拟根据关键词筛选
            keyword_results = []
            for result in mock_results:
                content_lower = result["content"].lower()
                if any(keyword.lower() in content_lower for keyword in keywords):
                    keyword_results.append(result)
            return keyword_results

        return mock_results

    def _extract_product_info(self, search_results: List[Dict]) -> List[Dict]:
        """从搜索结果中提取产品信息"""
        products = []

        for result in search_results:
            # 简单提取价格信息
            price_match = re.search(r'(\d+(?:\.\d+)?)\s*元', result["content"])
            price = price_match.group(1) if price_match else "未知"

            # 提取发布日期
            release_date = result["date"]

            # 简单分类
            product_type = "软件"
            if "AI" in result["title"] or "人工智能" in result["title"]:
                product_type = "AI产品"
            elif "企业" in result["title"] or "商业" in result["title"]:
                product_type = "企业方案"
            elif "融资" in result["title"] or "投资" in result["title"]:
                product_type = "公司动态"

            products.append({
                "title": result["title"],
                "type": product_type,
                "price": price,
                "release_date": release_date,
                "source": result["source"],
                "description": result["content"][:100] + "..."
            })

        return products

    def _format_as_table(self, products: List[Dict], timeframe_days: int) -> List[Dict]:
        """格式化产品信息为表格"""
        table_data = []

        for i, product in enumerate(products, 1):
            table_data.append({
                "序号": i,
                "产品名称": product["title"],
                "类型": product["type"],
                "价格": product["price"],
                "发布时间": product["release_date"],
                "来源": product["source"],
                "简要描述": product["description"]
            })

        return table_data

    def _generate_summary(self, products: List[Dict]) -> str:
        """生成调研摘要"""
        if not products:
            return "未找到相关产品信息"

        product_count = len(products)
        price_list = [float(p["price"]) for p in products if p["price"] != "未知" and p["price"].replace('.', '').isdigit()]

        summary = f"共找到 {product_count} 个相关产品。"

        if price_list:
            avg_price = sum(price_list) / len(price_list)
            summary += f"平均价格：{avg_price:.2f}元。"

        # 按类型统计
        type_counts = {}
        for product in products:
            p_type = product["type"]
            type_counts[p_type] = type_counts.get(p_type, 0) + 1

        if type_counts:
            type_summary = "、".join([f"{t}: {c}个" for t, c in type_counts.items()])
            summary += f"产品类型分布：{type_summary}。"

        return summary

    def price_comparison_shopping(self, product_name: str,
                                platforms: List[str] = None) -> Dict[str, Any]:
        """比价购物

        Args:
            product_name: 商品名称
            platforms: 电商平台列表，默认为["淘宝", "京东", "拼多多"]

        Returns:
            各平台价格比较结果
        """
        if platforms is None:
            platforms = ["淘宝", "京东", "拼多多"]

        logger.info(f"开始比价购物：{product_name}，平台：{', '.join(platforms)}")

        try:
            price_results = {}

            for platform in platforms:
                # 模拟在各平台搜索商品
                platform_prices = self._search_product_on_platform(product_name, platform)
                price_results[platform] = platform_prices

            # 找到最低价格
            best_deal = self._find_best_deal(price_results)

            # 添加到价格监控列表
            self._add_to_price_watch(product_name, price_results, best_deal)

            return {
                "success": True,
                "product": product_name,
                "price_results": price_results,
                "best_deal": best_deal,
                "recommendation": self._generate_price_recommendation(best_deal)
            }

        except Exception as e:
            logger.error(f"比价购物失败: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    def _search_product_on_platform(self, product_name: str, platform: str) -> List[Dict]:
        """在指定平台搜索商品（模拟）"""
        time.sleep(0.5)  # 模拟网络延迟

        # 模拟不同平台的价格数据
        if platform == "淘宝":
            return [
                {"seller": "官方旗舰店", "price": 299.0, "sales": 1000, "rating": 4.8},
                {"seller": "品牌专卖店", "price": 289.0, "sales": 500, "rating": 4.7},
                {"seller": "授权经销商", "price": 279.0, "sales": 200, "rating": 4.6}
            ]
        elif platform == "京东":
            return [
                {"seller": "京东自营", "price": 305.0, "sales": 800, "rating": 4.9},
                {"seller": "品牌官方店", "price": 295.0, "sales": 300, "rating": 4.8},
                {"seller": "第三方卖家", "price": 285.0, "sales": 150, "rating": 4.5}
            ]
        elif platform == "拼多多":
            return [
                {"seller": "品牌补贴店", "price": 269.0, "sales": 1500, "rating": 4.6},
                {"seller": "工厂直供", "price": 259.0, "sales": 800, "rating": 4.5},
                {"seller": "团购专享", "price": 249.0, "sales": 5000, "rating": 4.7}
            ]
        else:
            return [
                {"seller": "默认卖家", "price": 300.0, "sales": 100, "rating": 4.0}
            ]

    def _find_best_deal(self, price_results: Dict[str, List[Dict]]) -> Dict[str, Any]:
        """找到最佳优惠"""
        best_price = float('inf')
        best_deal = None

        for platform, deals in price_results.items():
            for deal in deals:
                if deal["price"] < best_price:
                    best_price = deal["price"]
                    best_deal = {
                        "platform": platform,
                        "seller": deal["seller"],
                        "price": deal["price"],
                        "sales": deal.get("sales", 0),
                        "rating": deal.get("rating", 0)
                    }

        return best_deal

    def _add_to_price_watch(self, product_name: str, price_results: Dict, best_deal: Dict):
        """添加到价格监控列表"""
        watch_id = f"{product_name}_{int(time.time())}"

        self.price_watch_list[watch_id] = {
            "product": product_name,
            "added_date": datetime.now().isoformat(),
            "current_best_price": best_deal["price"] if best_deal else None,
            "price_history": {
                datetime.now().isoformat(): {
                    platform: min([deal["price"] for deal in deals])
                    for platform, deals in price_results.items()
                }
            },
            "monitoring": True
        }

        self.save_research_data()
        logger.info(f"已将 {product_name} 添加到价格监控列表")

    def _generate_price_recommendation(self, best_deal: Dict) -> str:
        """生成购买建议"""
        if not best_deal:
            return "暂无购买建议"

        platform = best_deal["platform"]
        price = best_deal["price"]
        seller = best_deal["seller"]
        rating = best_deal.get("rating", 0)

        recommendation = f"建议在 {platform} 的 {seller} 购买，价格 {price}元"

        if rating >= 4.8:
            recommendation += "，该卖家评分很高，值得信赖。"
        elif rating >= 4.5:
            recommendation += "，该卖家评分良好，可以考虑。"
        else:
            recommendation += "，请注意卖家评分较低。"

        return recommendation

    def monitor_and_alert_price(self, watch_id: str, target_price: float = None) -> bool:
        """监控价格并提醒

        Args:
            watch_id: 监控项ID
            target_price: 目标价格

        Returns:
            是否启动监控
        """
        if watch_id not in self.price_watch_list:
            logger.error(f"监控项不存在: {watch_id}")
            return False

        # 启动监控线程
        monitor_thread = threading.Thread(
            target=self._price_monitor_worker,
            args=(watch_id, target_price),
            daemon=True
        )
        monitor_thread.start()

        logger.info(f"已启动价格监控: {watch_id}")
        return True

    def _price_monitor_worker(self, watch_id: str, target_price: float = None):
        """价格监控工作线程"""
        watch_item = self.price_watch_list[watch_id]
        product_name = watch_item["product"]

        logger.info(f"开始监控商品价格: {product_name}")

        try:
            while watch_item.get("monitoring", True):
                # 检查当前价格
                current_price = self._check_current_price(product_name)

                # 记录价格历史
                current_time = datetime.now().isoformat()
                if "price_history" not in watch_item:
                    watch_item["price_history"] = {}

                watch_item["price_history"][current_time] = current_price

                # 检查是否达到目标价格
                if target_price and current_price["best_price"] <= target_price:
                    logger.info(f"🎉 {product_name} 价格已降至目标价格以下！当前最低价: {current_price['best_price']}元")
                    # 这里可以添加通知逻辑（如发送微信消息）

                # 检查价格变化
                self._check_price_change(watch_id, current_price)

                # 保存更新
                self.save_research_data()

                # 等待一段时间后再次检查
                time.sleep(3600)  # 每小时检查一次

        except Exception as e:
            logger.error(f"价格监控出错: {e}")

    def _check_current_price(self, product_name: str) -> Dict[str, Any]:
        """检查当前价格（模拟）"""

        platforms = ["淘宝", "京东", "拼多多"]
        prices = {}

        for platform in platforms:
            base_price = 250 + random.randint(-20, 20)
            prices[platform] = {
                "price": base_price,
                "seller": f"{platform}模拟卖家",
                "timestamp": datetime.now().isoformat()
            }

        best_platform = min(prices.keys(), key=lambda p: prices[p]["price"])
        best_price = prices[best_platform]["price"]

        return {
            "platforms": prices,
            "best_platform": best_platform,
            "best_price": best_price,
            "check_time": datetime.now().isoformat()
        }

    def _check_price_change(self, watch_id: str, current_price: Dict[str, Any]):
        """检查价格变化"""
        watch_item = self.price_watch_list[watch_id]
        price_history = watch_item.get("price_history", {})

        if len(price_history) < 2:
            return

        # 获取历史价格
        history_times = sorted(price_history.keys())
        previous_time = history_times[-2]
        current_time = history_times[-1]

        previous_best = min(price_history[previous_time].values())
        current_best = min(price_history[current_time].values())

        price_change = current_best - previous_best

        if price_change < 0:
            logger.info(f"📉 {watch_item['product']} 价格下降 {abs(price_change):.2f}元")
        elif price_change > 0:
            logger.warning(f"📈 {watch_item['product']} 价格上涨 {price_change:.2f}元")

    def ticket_grabber(self, event_name: str, target_url: str,
                      target_date: str, max_price: float = None) -> Dict[str, Any]:
        """抢票功能

        Args:
            event_name: 活动/票务名称
            target_url: 目标网址
            target_date: 目标日期
            max_price: 最高可接受价格

        Returns:
            抢票任务状态
        """
        logger.info(f"创建抢票任务：{event_name}，目标日期：{target_date}")

        ticket_id = f"ticket_{int(time.time())}"

        # 创建监控任务
        self.ticket_monitors[ticket_id] = {
            "event_name": event_name,
            "target_url": target_url,
            "target_date": target_date,
            "max_price": max_price,
            "status": "monitoring",
            "created_at": datetime.now().isoformat(),
            "last_checked": None,
            "tickets_found": []
        }

        # 启动监控线程
        monitor_thread = threading.Thread(
            target=self._ticket_monitor_worker,
            args=(ticket_id,),
            daemon=True
        )
        monitor_thread.start()

        return {
            "success": True,
            "ticket_id": ticket_id,
            "event_name": event_name,
            "status": "monitoring_started",
            "message": f"已开始监控 {event_name} 的票务信息"
        }

    def _ticket_monitor_worker(self, ticket_id: str):
        """票务监控工作线程"""
        ticket_info = self.ticket_monitors[ticket_id]
        event_name = ticket_info["event_name"]

        logger.info(f"开始监控票务：{event_name}")

        try:
            while ticket_info.get("status") == "monitoring":
                # 检查票务状态
                tickets_available = self._check_ticket_availability(ticket_info)

                if tickets_available:
                    logger.info(f"🎫 发现可用票务：{event_name}")

                    # 尝试自动购买
                    success = self._attempt_ticket_purchase(ticket_info, tickets_available)

                    if success:
                        ticket_info["status"] = "purchased"
                        logger.info(f"✅ 成功购买票务：{event_name}")
                        break

                # 更新检查时间
                ticket_info["last_checked"] = datetime.now().isoformat()

                # 等待一段时间后再次检查
                time.sleep(300)  # 每5分钟检查一次

        except Exception as e:
            logger.error(f"票务监控出错: {e}")
            ticket_info["status"] = "error"
            ticket_info["error"] = str(e)

    def _check_ticket_availability(self, ticket_info: Dict) -> List[Dict]:
        """检查票务可用性（模拟）"""
        # 模拟票务检查
        event_name = ticket_info["event_name"]
        target_date = ticket_info["target_date"]
        max_price = ticket_info["max_price"]

        if random.random() < 0.3:  # 30%概率有票
            tickets = []
            ticket_types = ["普通票", "VIP票", "学生票"]

            for i in range(random.randint(1, 3)):
                ticket_type = random.choice(ticket_types)
                price = random.randint(100, 1000)

                # 检查价格限制
                if max_price and price > max_price:
                    continue

                tickets.append({
                    "type": ticket_type,
                    "price": price,
                    "seat": f"{random.randint(1, 50)}排{random.randint(1, 30)}座",
                    "available": True
                })

            return tickets

        return []

    def _attempt_ticket_purchase(self, ticket_info: Dict, tickets: List[Dict]) -> bool:
        """尝试购买票务（模拟）"""
        # 选择最合适的票
        if not tickets:
            return False

        # 如果有价格限制，选择价格最低的
        if ticket_info["max_price"]:
            affordable_tickets = [t for t in tickets if t["price"] <= ticket_info["max_price"]]
            if not affordable_tickets:
                return False
            selected_ticket = min(affordable_tickets, key=lambda t: t["price"])
        else:
            selected_ticket = tickets[0]

        # 模拟购买过程
        logger.info(f"尝试购买票务：{selected_ticket['type']}，价格：{selected_ticket['price']}元")
        time.sleep(2)  # 模拟购买延迟

        success = random.random() < 0.8

        if success:
            ticket_info["purchased_ticket"] = selected_ticket
            ticket_info["purchase_time"] = datetime.now().isoformat()

        return success

    def get_research_history(self, limit: int = 10) -> List[Dict]:
        """获取研究历史"""
        return self.research_history[-limit:] if self.research_history else []

    def get_price_watch_list(self) -> Dict[str, Dict]:
        """获取价格监控列表"""
        return self.price_watch_list

    def get_active_ticket_monitors(self) -> Dict[str, Dict]:
        """获取活跃的票务监控器"""
        active = {}
        for ticket_id, info in self.ticket_monitors.items():
            if info.get("status") in ["monitoring", "purchased"]:
                active[ticket_id] = info
        return active