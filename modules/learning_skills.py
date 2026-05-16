import logging
import json
import time
import re
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
import threading
import queue

logger = logging.getLogger("LearningSkills")

# 导入可选依赖
try:
    from deep_translator import GoogleTranslator
    DEEP_TRANSLATOR_AVAILABLE = True
except ImportError:
    DEEP_TRANSLATOR_AVAILABLE = False
    GoogleTranslator = None
    logger.warning("deep_translator模块未安装，会议同传功能受限。请运行: pip install deep_translator")

try:
    import pandas
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False
    pandas = None
    logger.warning("pandas模块未安装，数据分析功能受限。请运行: pip install pandas")

try:
    import openpyxl
    OPENPYXL_AVAILABLE = True
except ImportError:
    OPENPYXL_AVAILABLE = False
    openpyxl = None
    logger.warning("openpyxl模块未安装，Excel文件读取功能受限。请运行: pip install openpyxl")

try:
    import matplotlib.pyplot as plt
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False
    plt = None
    logger.warning("matplotlib模块未安装，数据可视化功能受限。请运行: pip install matplotlib")

try:
    import seaborn as sns
    SEABORN_AVAILABLE = True
except ImportError:
    SEABORN_AVAILABLE = False
    sns = None
    logger.warning("seaborn模块未安装，数据可视化功能受限。请运行: pip install seaborn")


try:
    import speech_recognition as sr
    SPEECH_RECOGNITION_AVAILABLE = True
except ImportError:
    SPEECH_RECOGNITION_AVAILABLE = False
    sr = None
    logger.warning("speech_recognition库未安装，语音识别功能不可用。请运行: pip install SpeechRecognition")

class LearningSkills:
    """学习与辅助决策技能模块 - 会议同传、游戏攻略、数据分析等功能"""

    def __init__(self, config_manager=None):
        self.config_manager = config_manager
        self.meeting_transcripts = []  # 会议记录
        self.game_guides = {}          # 游戏攻略缓存
        self.data_analysis_history = [] # 数据分析历史
        self.load_learning_data()

        # 初始化语音识别（可选）
        self.speech_recognizer = None
        self._init_speech_recognition()

    def load_learning_data(self):
        """加载学习数据"""
        data_dir = Path(__file__).parent.parent / "knowledge_base" / "data"
        data_dir.mkdir(parents=True, exist_ok=True)

        # 加载会议记录
        meetings_file = data_dir / "meeting_transcripts.json"
        if meetings_file.exists():
            try:
                with open(meetings_file, 'r', encoding='utf-8') as f:
                    self.meeting_transcripts = json.load(f)
                logger.info(f"已加载 {len(self.meeting_transcripts)} 条会议记录")
            except Exception as e:
                logger.error(f"加载会议记录失败: {e}")

        # 加载游戏攻略缓存
        guides_file = data_dir / "game_guides.json"
        if guides_file.exists():
            try:
                with open(guides_file, 'r', encoding='utf-8') as f:
                    self.game_guides = json.load(f)
                logger.info(f"已加载 {len(self.game_guides)} 个游戏攻略缓存")
            except Exception as e:
                logger.error(f"加载游戏攻略缓存失败: {e}")

    def save_learning_data(self):
        """保存学习数据"""
        data_dir = Path(__file__).parent.parent / "knowledge_base" / "data"
        data_dir.mkdir(parents=True, exist_ok=True)

        # 保存会议记录
        meetings_file = data_dir / "meeting_transcripts.json"
        try:
            with open(meetings_file, 'w', encoding='utf-8') as f:
                json.dump(self.meeting_transcripts, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存会议记录失败: {e}")

        # 保存游戏攻略缓存
        guides_file = data_dir / "game_guides.json"
        try:
            with open(guides_file, 'w', encoding='utf-8') as f:
                json.dump(self.game_guides, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存游戏攻略缓存失败: {e}")

    def _init_speech_recognition(self):
        """初始化语音识别"""
        if not SPEECH_RECOGNITION_AVAILABLE:
            logger.warning("speech_recognition库未安装，语音识别功能不可用")
            return
        try:
            self.speech_recognizer = sr.Recognizer()
            logger.info("语音识别初始化成功")
        except Exception as e:
            logger.error(f"语音识别初始化失败: {e}")

    def real_time_meeting_translation(self, source_lang: str = "zh-CN",
                                    target_lang: str = "en",
                                    duration_minutes: int = 60) -> Dict[str, Any]:
        """实时会议同传

        Args:
            source_lang: 源语言
            target_lang: 目标语言
            duration_minutes: 持续时间（分钟）

        Returns:
            会议同传任务状态
        """
        logger.info(f"开始会议同传：{source_lang} -> {target_lang}，持续时间：{duration_minutes}分钟")

        if not self.speech_recognizer:
            return {
                "success": False,
                "error": "语音识别未初始化，请安装speech_recognition和pyaudio"
            }

        try:
            # 创建会议记录
            meeting_id = f"meeting_{int(time.time())}"
            meeting_record = {
                "meeting_id": meeting_id,
                "source_lang": source_lang,
                "target_lang": target_lang,
                "start_time": datetime.now().isoformat(),
                "duration": duration_minutes,
                "transcripts": [],
                "translations": []
            }

            # 启动同传线程
            trans_thread = threading.Thread(
                target=self._meeting_translation_worker,
                args=(meeting_id, source_lang, target_lang, duration_minutes),
                daemon=True
            )
            trans_thread.start()

            return {
                "success": True,
                "meeting_id": meeting_id,
                "message": f"已开始会议同传：{source_lang} -> {target_lang}",
                "status": "started"
            }

        except Exception as e:
            logger.error(f"启动会议同传失败: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    def _meeting_translation_worker(self, meeting_id: str, source_lang: str,
                                  target_lang: str, duration_minutes: int):
        """会议同传工作线程"""
        logger.info(f"会议同传工作线程启动：{meeting_id}")

        try:
            # 检查依赖是否可用
            if not SPEECH_RECOGNITION_AVAILABLE:
                logger.error("speech_recognition库未安装，无法进行会议同传。请运行: pip install SpeechRecognition")
                return

            # 检查googletrans是否可用
            if not DEEP_TRANSLATOR_AVAILABLE:
                logger.error("googletrans模块未安装，无法进行翻译。请运行: pip install googletrans")
                return

            translator = GoogleTranslator(source=source_lang.split('-')[0], target=target_lang.split('-')[0])
            end_time = time.time() + duration_minutes * 60

            # 使用麦克风
            with sr.Microphone() as source:
                self.speech_recognizer.adjust_for_ambient_noise(source)

                while time.time() < end_time:
                    try:
                        # 监听语音
                        logger.info("正在监听语音...")
                        audio = self.speech_recognizer.listen(source, timeout=5, phrase_time_limit=10)

                        # 识别语音
                        text = self.speech_recognizer.recognize_google(audio, language=source_lang)
                        logger.info(f"识别结果：{text}")

                        # 翻译文本
                        translated_text = translator.translate(text)
                        logger.info(f"翻译结果：{translated_text}")

                        # 保存记录
                        transcript_entry = {
                            "timestamp": datetime.now().isoformat(),
                            "original": text,
                            "translated": translated_text,
                            "source_lang": source_lang,
                            "target_lang": target_lang
                        }

                        # 添加到会议记录
                        for record in self.meeting_transcripts:
                            if record.get("meeting_id") == meeting_id:
                                record["transcripts"].append(transcript_entry)
                                break

                        # 生成双语字幕（这里可以发送到UI或文件）
                        self._generate_bilingual_subtitle(text, translated_text)

                    except sr.WaitTimeoutError:
                        logger.debug("语音监听超时")
                    except sr.UnknownValueError:
                        logger.warning("无法识别语音")
                    except sr.RequestError as e:
                        logger.error(f"语音识别服务错误: {e}")
                    except Exception as e:
                        logger.error(f"翻译处理错误: {e}")

                    time.sleep(0.5)

            logger.info(f"会议同传结束：{meeting_id}")

        except Exception as e:
            logger.error(f"会议同传工作线程出错: {e}")

    def _generate_bilingual_subtitle(self, original: str, translated: str):
        """生成双语字幕"""
        # 这里可以输出到文件或UI
        subtitle_line = f"[{datetime.now().strftime('%H:%M:%S')}] {original} | {translated}"
        logger.info(f"双语字幕：{subtitle_line}")

        # 可以保存到文件
        subtitle_file = Path.home() / "meeting_subtitles.txt"
        with open(subtitle_file, 'a', encoding='utf-8') as f:
            f.write(subtitle_line + "\n")

    def game_strategy_helper(self, game_name: str, current_situation: str = None) -> Dict[str, Any]:
        """游戏攻略助手

        Args:
            game_name: 游戏名称
            current_situation: 当前游戏情况描述

        Returns:
            游戏攻略建议
        """
        logger.info(f"游戏攻略助手：{game_name}")

        try:
            # 检查缓存
            if game_name in self.game_guides:
                cached_guide = self.game_guides[game_name]
                logger.info(f"使用缓存的游戏攻略：{game_name}")
                return {
                    "success": True,
                    "game": game_name,
                    "from_cache": True,
                    "guide": cached_guide
                }

            # 模拟获取游戏攻略
            guide = self._fetch_game_guide(game_name, current_situation)

            # 缓存攻略
            self.game_guides[game_name] = guide
            self.save_learning_data()

            return {
                "success": True,
                "game": game_name,
                "from_cache": False,
                "guide": guide
            }

        except Exception as e:
            logger.error(f"获取游戏攻略失败: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    def _fetch_game_guide(self, game_name: str, situation: str = None) -> Dict[str, Any]:
        """获取游戏攻略（模拟）"""
        # 模拟网络搜索
        time.sleep(1)

        # 常见游戏的模拟攻略
        common_guides = {
            "原神": {
                "tips": [
                    "优先升级主角和常用角色",
                    "每日完成日常任务获取原石",
                    "合理分配树脂刷取材料",
                    "探索地图解锁传送点"
                ],
                "combat": "利用元素反应提升伤害",
                "resources": "每周记得打周本BOSS",
                "events": "关注限时活动获取稀有奖励"
            },
            "英雄联盟": {
                "tips": [
                    "补刀是关键，练习最后一下",
                    "关注小地图，注意敌人动向",
                    "根据对手选择符文和装备",
                    "与队友沟通，团队合作"
                ],
                "roles": "明确自己的位置和职责",
                "objectives": "优先推塔和拿龙",
                "teamfights": "集中火力击杀对方核心"
            },
            "王者荣耀": {
                "tips": [
                    "熟悉英雄技能和连招",
                    "合理利用草丛进行埋伏",
                    "注意经济差距及时发育",
                    "配合队友进行团战"
                ],
                "heroes": "根据阵容选择英雄",
                "strategy": "推塔优先于杀人",
                "ranking": "赛季末冲分注意时间"
            }
        }

        if game_name in common_guides:
            guide = common_guides[game_name]
        else:
            guide = {
                "tips": [
                    f"在网上搜索'{game_name} 最新攻略'",
                    "查看游戏官方社区和论坛",
                    "观看高手直播学习技巧",
                    "多加练习熟悉游戏机制"
                ],
                "general": "每个游戏都有其独特机制，需要时间掌握",
                "resources": "推荐B站、贴吧、NGA等社区"
            }

        # 如果有当前情况，尝试提供针对性建议
        if situation:
            guide["situation_advice"] = self._analyze_game_situation(situation)

        return guide

    def _analyze_game_situation(self, situation: str) -> str:
        """分析游戏情况（简单关键词匹配）"""
        situation_lower = situation.lower()

        if any(word in situation_lower for word in ["卡关", "过不去", "打不过", "困难"]):
            return "建议降低难度、提升角色等级或寻找攻略视频学习打法。"
        elif any(word in situation_lower for word in ["资源", "材料", "金币", "缺乏"]):
            return "优先完成日常和周常任务，合理规划资源使用。"
        elif any(word in situation_lower for word in ["队友", "合作", "组队", "配合"]):
            return "与队友沟通战术，明确各自职责，保持良好心态。"
        elif any(word in situation_lower for word in ["装备", "武器", "build", "配装"]):
            return "参考主流配装方案，根据自身需求进行调整。"
        else:
            return "建议详细描述遇到的问题，或提供截图以便更准确分析。"

    def excel_data_analysis(self, file_path: str, analysis_type: str = "basic") -> Dict[str, Any]:
        """Excel数据分析

        Args:
            file_path: Excel文件路径
            analysis_type: 分析类型（basic/statistical/visualization）

        Returns:
            分析结果
        """
        logger.info(f"Excel数据分析：{file_path}，类型：{analysis_type}")

        # 检查必要依赖
        if not PANDAS_AVAILABLE:
            logger.error("pandas模块未安装，无法进行数据分析。请运行: pip install pandas")
            return {
                "success": False,
                "error": "pandas模块未安装，无法进行数据分析。请运行: pip install pandas"
            }

        if not OPENPYXL_AVAILABLE:
            logger.error("openpyxl模块未安装，无法读取Excel文件。请运行: pip install openpyxl")
            return {
                "success": False,
                "error": "openpyxl模块未安装，无法读取Excel文件。请运行: pip install openpyxl"
            }

        # 如果是可视化分析，检查matplotlib和seaborn
        if analysis_type == "visualization":
            if not MATPLOTLIB_AVAILABLE or not SEABORN_AVAILABLE:
                logger.error("matplotlib或seaborn模块未安装，无法进行可视化分析。请运行: pip install matplotlib seaborn")
                return {
                    "success": False,
                    "error": "matplotlib或seaborn模块未安装，无法进行可视化分析。请运行: pip install matplotlib seaborn"
                }

        try:
            # 读取Excel文件
            df = pandas.read_excel(file_path)

            analysis_result = {
                "file": file_path,
                "analysis_type": analysis_type,
                "timestamp": datetime.now().isoformat(),
                "basic_info": {
                    "rows": len(df),
                    "columns": len(df.columns),
                    "column_names": list(df.columns),
                    "data_types": {col: str(dtype) for col, dtype in df.dtypes.items()}
                }
            }

            # 基本分析
            if analysis_type == "basic":
                analysis_result["summary"] = self._basic_data_summary(df)

            # 统计分析
            elif analysis_type == "statistical":
                analysis_result["statistics"] = self._statistical_analysis(df)

            # 可视化分析
            elif analysis_type == "visualization":
                chart_path = self._create_data_visualization(df, file_path)
                analysis_result["visualization"] = {
                    "chart_created": True,
                    "chart_path": chart_path
                }

            # 异常检测
            analysis_result["anomalies"] = self._detect_anomalies(df)

            # 保存分析历史
            self.data_analysis_history.append(analysis_result)

            return {
                "success": True,
                "analysis": analysis_result,
                "recommendations": self._generate_data_recommendations(analysis_result)
            }

        except Exception as e:
            logger.error(f"Excel数据分析失败: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    def _basic_data_summary(self, df) -> Dict[str, Any]:
        """基本数据摘要"""
        summary = {
            "total_records": len(df),
            "total_columns": len(df.columns),
            "missing_values": df.isnull().sum().to_dict(),
            "unique_counts": {col: df[col].nunique() for col in df.columns if df[col].dtype == 'object'},
            "sample_data": df.head(5).to_dict('records')
        }

        # 数值列统计
        numeric_cols = df.select_dtypes(include=['number']).columns
        if len(numeric_cols) > 0:
            summary["numeric_summary"] = df[numeric_cols].describe().to_dict()

        return summary

    def _statistical_analysis(self, df) -> Dict[str, Any]:
        """统计分析"""
        stats = {}

        # 数值列
        numeric_cols = df.select_dtypes(include=['number']).columns
        for col in numeric_cols:
            stats[col] = {
                "mean": df[col].mean(),
                "median": df[col].median(),
                "std": df[col].std(),
                "min": df[col].min(),
                "max": df[col].max(),
                "skewness": df[col].skew(),
                "kurtosis": df[col].kurtosis()
            }

        # 相关性分析
        if len(numeric_cols) > 1:
            correlation = df[numeric_cols].corr()
            stats["correlation"] = correlation.to_dict()

            # 找到强相关关系
            strong_correlations = []
            for i in range(len(numeric_cols)):
                for j in range(i+1, len(numeric_cols)):
                    corr_value = abs(correlation.iloc[i, j])
                    if corr_value > 0.7:
                        strong_correlations.append({
                            "col1": numeric_cols[i],
                            "col2": numeric_cols[j],
                            "correlation": corr_value
                        })
            stats["strong_correlations"] = strong_correlations

        return stats

    def _create_data_visualization(self, df, file_path: str) -> str:
        """创建数据可视化"""
        # 检查必要依赖
        if not MATPLOTLIB_AVAILABLE or not SEABORN_AVAILABLE:
            logger.error("matplotlib或seaborn模块未安装，无法创建可视化。请运行: pip install matplotlib seaborn")
            return "matplotlib或seaborn模块未安装，无法创建可视化。请运行: pip install matplotlib seaborn"

        try:
            # 创建输出目录
            output_dir = Path(file_path).parent / "visualizations"
            output_dir.mkdir(exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

            # 1. 数值分布直方图
            numeric_cols = df.select_dtypes(include=['number']).columns
            if len(numeric_cols) > 0:
                fig, axes = plt.subplots(min(3, len(numeric_cols)), 1, figsize=(10, 3*min(3, len(numeric_cols))))
                if len(numeric_cols) == 1:
                    axes = [axes]

                for idx, col in enumerate(numeric_cols[:3]):
                    axes[idx].hist(df[col].dropna(), bins=20, edgecolor='black')
                    axes[idx].set_title(f'{col} Distribution')
                    axes[idx].set_xlabel(col)
                    axes[idx].set_ylabel('Frequency')

                plt.tight_layout()
                hist_path = output_dir / f"histograms_{timestamp}.png"
                plt.savefig(hist_path)
                plt.close()

            # 2. 相关性热图
            if len(numeric_cols) > 1:
                plt.figure(figsize=(8, 6))
                correlation = df[numeric_cols].corr()
                sns.heatmap(correlation, annot=True, cmap='coolwarm', center=0)
                plt.title('Correlation Heatmap')

                heatmap_path = output_dir / f"heatmap_{timestamp}.png"
                plt.savefig(heatmap_path)
                plt.close()

                return str(heatmap_path)
            elif len(numeric_cols) == 1:
                return str(hist_path)
            else:
                return "无数值数据，无法创建可视化"

        except Exception as e:
            logger.error(f"创建可视化失败: {e}")
            return f"可视化创建失败: {e}"

    def _detect_anomalies(self, df) -> Dict[str, Any]:
        """检测数据异常"""
        anomalies = {
            "missing_values": {},
            "outliers": {},
            "data_quality_issues": []
        }

        # 缺失值检测
        missing = df.isnull().sum()
        for col, count in missing.items():
            if count > 0:
                anomalies["missing_values"][col] = {
                    "count": int(count),
                    "percentage": float(count / len(df) * 100)
                }

        # 异常值检测（简单IQR方法）
        numeric_cols = df.select_dtypes(include=['number']).columns
        for col in numeric_cols:
            Q1 = df[col].quantile(0.25)
            Q3 = df[col].quantile(0.75)
            IQR = Q3 - Q1
            lower_bound = Q1 - 1.5 * IQR
            upper_bound = Q3 + 1.5 * IQR

            outliers = df[(df[col] < lower_bound) | (df[col] > upper_bound)]
            if len(outliers) > 0:
                anomalies["outliers"][col] = {
                    "count": len(outliers),
                    "percentage": len(outliers) / len(df) * 100,
                    "min_outlier": float(outliers[col].min()),
                    "max_outlier": float(outliers[col].max())
                }

        # 数据质量问题
        for col in df.columns:
            # 检查列名是否规范
            if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', str(col)):
                anomalies["data_quality_issues"].append(f"列名 '{col}' 不符合命名规范")

            # 检查数据类型一致性
            if df[col].dtype == 'object':
                # 检查是否有混合类型
                sample_values = df[col].dropna().unique()[:10]
                if len(sample_values) > 0:
                    types = set(type(val).__name__ for val in sample_values)
                    if len(types) > 1:
                        anomalies["data_quality_issues"].append(f"列 '{col}' 包含混合数据类型: {types}")

        return anomalies

    def _generate_data_recommendations(self, analysis_result: Dict) -> List[str]:
        """生成数据建议"""
        recommendations = []

        basic_info = analysis_result.get("basic_info", {})
        anomalies = analysis_result.get("anomalies", {})

        # 缺失值建议
        missing_values = anomalies.get("missing_values", {})
        for col, info in missing_values.items():
            if info["percentage"] > 20:
                recommendations.append(f"列 '{col}' 缺失值较多（{info['percentage']:.1f}%），建议检查数据收集过程")
            elif info["percentage"] > 0:
                recommendations.append(f"列 '{col}' 有 {info['count']} 个缺失值，可考虑填充或删除")

        # 异常值建议
        outliers = anomalies.get("outliers", {})
        for col, info in outliers.items():
            if info["percentage"] > 5:
                recommendations.append(f"列 '{col}' 异常值较多（{info['percentage']:.1f}%），建议检查数据准确性")

        # 数据质量建议
        issues = anomalies.get("data_quality_issues", [])
        for issue in issues:
            recommendations.append(f"数据质量问题：{issue}")

        # 通用建议
        if basic_info.get("rows", 0) < 100:
            recommendations.append("数据量较小，统计分析结果可能不够可靠")

        if len(basic_info.get("column_names", [])) > 20:
            recommendations.append("列数较多，建议进行特征选择或降维处理")

        return recommendations

    def get_meeting_transcripts(self, limit: int = 10) -> List[Dict]:
        """获取会议记录"""
        return self.meeting_transcripts[-limit:] if self.meeting_transcripts else []

    def get_data_analysis_history(self, limit: int = 10) -> List[Dict]:
        """获取数据分析历史"""
        return self.data_analysis_history[-limit:] if self.data_analysis_history else []

    def clear_game_guides_cache(self) -> bool:
        """清空游戏攻略缓存"""
        try:
            self.game_guides = {}
            self.save_learning_data()
            logger.info("已清空游戏攻略缓存")
            return True
        except Exception as e:
            logger.error(f"清空游戏攻略缓存失败: {e}")
            return False