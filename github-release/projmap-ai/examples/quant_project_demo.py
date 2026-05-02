"""量化策略项目案例演示

模拟一个完整的量化策略项目，展示增强后的脉络图生成效果。
"""

import json
from datetime import datetime


QUANT_PROJECT_FILES = {
    "data_fetch.py": '''
import pandas as pd
import requests
from config.settings import API_KEY, DB_CONFIG

def fetch_stock_data(ticker, start_date, end_date):
    """从API获取股票数据"""
    url = f"https://api.example.com/stocks/{ticker}"
    response = requests.get(url, headers={"Authorization": API_KEY})
    data = response.json()
    df = pd.DataFrame(data)
    df.to_csv(f"data/raw/{ticker}_raw.csv")
    return df

def fetch_market_data():
    """获取市场整体数据"""
    df = pd.read_parquet("data/market.parquet")
    return df
''',
    
    "clean.py": '''
import pandas as pd
import numpy as np

def clean_data(input_path, output_path):
    """数据清洗"""
    df = pd.read_csv(input_path)
    
    df = df.dropna()
    df = df.drop_duplicates()
    
    df['returns'] = df['close'].pct_change()
    
    df.to_csv(output_path, index=False)
    return df

def handle_outliers(df, threshold=3):
    """处理异常值"""
    z_scores = np.abs((df - df.mean()) / df.std())
    return df[(z_scores < threshold).all(axis=1)]
''',
    
    "feature_eng.py": '''
import pandas as pd
import numpy as np
from scipy import stats

def generate_features(df):
    """生成技术指标特征"""
    df['sma_20'] = df['close'].rolling(20).mean()
    df['sma_50'] = df['close'].rolling(50).mean()
    df['rsi'] = calculate_rsi(df['close'])
    df['macd'] = calculate_macd(df['close'])
    
    df.to_csv("data/features/features.csv", index=False)
    return df

def calculate_rsi(prices, period=14):
    """计算RSI指标"""
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def calculate_macd(prices):
    """计算MACD指标"""
    ema_12 = prices.ewm(span=12).mean()
    ema_26 = prices.ewm(span=26).mean()
    return ema_12 - ema_26
''',
    
    "model_train.py": '''
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
import joblib

def train_model(features_path, model_path):
    """训练预测模型"""
    df = pd.read_csv(features_path)
    
    X = df.drop(['target', 'date'], axis=1)
    y = df['target']
    
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, shuffle=False
    )
    
    model = RandomForestClassifier(n_estimators=100, max_depth=10)
    model.fit(X_train, y_train)
    
    joblib.dump(model, model_path)
    
    pd.DataFrame({
        'feature': X.columns,
        'importance': model.feature_importances_
    }).to_csv("results/feature_importance.csv", index=False)
    
    return model

def load_model(model_path):
    """加载已训练模型"""
    return joblib.load(model_path)
''',
    
    "backtest.py": '''
import pandas as pd
import numpy as np
from model_train import load_model

class BacktestEngine:
    def __init__(self, initial_capital=100000):
        self.initial_capital = initial_capital
        self.capital = initial_capital
        self.positions = []
        
    def run_backtest(self, data_path, model_path):
        """运行回测"""
        df = pd.read_csv(data_path)
        model = load_model(model_path)
        
        features = df.drop(['date', 'target'], axis=1)
        predictions = model.predict(features)
        
        df['signal'] = predictions
        df['returns'] = df['close'].pct_change()
        df['strategy_returns'] = df['signal'].shift(1) * df['returns']
        
        df.to_csv("results/backtest_results.csv", index=False)
        
        metrics = self.calculate_metrics(df['strategy_returns'])
        return metrics
    
    def calculate_metrics(self, returns):
        """计算策略指标"""
        return {
            'total_return': (1 + returns).prod() - 1,
            'sharpe_ratio': returns.mean() / returns.std() * np.sqrt(252),
            'max_drawdown': (returns.cumsum().expanding().max() - returns.cumsum()).max(),
            'win_rate': (returns > 0).mean()
        }
''',
    
    "config/settings.py": '''
import os
import yaml

API_KEY = os.getenv("QUANT_API_KEY")
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "database": "quant_db"
}

def load_config(config_path="config/config.yaml"):
    """加载配置文件"""
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)
''',
    
    "main.py": '''
from data_fetch import fetch_stock_data, fetch_market_data
from clean import clean_data
from feature_eng import generate_features
from model_train import train_model
from backtest import BacktestEngine

def main():
    """主流程"""
    ticker = "AAPL"
    
    raw_data = fetch_stock_data(ticker, "2020-01-01", "2023-12-31")
    
    clean_data(
        f"data/raw/{ticker}_raw.csv",
        f"data/clean/{ticker}_clean.csv"
    )
    
    df = pd.read_csv(f"data/clean/{ticker}_clean.csv")
    features = generate_features(df)
    
    train_model("data/features/features.csv", "models/rf_model.pkl")
    
    engine = BacktestEngine(initial_capital=100000)
    metrics = engine.run_backtest(
        "data/features/features.csv",
        "models/rf_model.pkl"
    )
    
    print(f"策略收益: {metrics['total_return']:.2%}")
    print(f"夏普比率: {metrics['sharpe_ratio']:.2f}")

if __name__ == "__main__":
    main()
''',
    
    "config/config.yaml": '''
database:
  host: localhost
  port: 5432
  name: quant_db

api:
  base_url: https://api.example.com
  timeout: 30

model:
  type: random_forest
  n_estimators: 100
  max_depth: 10

backtest:
  initial_capital: 100000
  commission: 0.001
'''
}


def generate_quant_project_demo():
    """生成量化策略项目的脉络图演示数据"""
    
    nodes = [
        {
            "id": "main.py",
            "label": "main.py",
            "node_type": "file",
            "display_name": "主入口",
            "file_count": 1,
            "total_lines": 30,
            "importance_score": 1.0,
            "is_collapsed": False
        },
        {
            "id": "data_fetch.py",
            "label": "data_fetch.py",
            "node_type": "file",
            "display_name": "数据采集",
            "file_count": 1,
            "total_lines": 25,
            "importance_score": 0.9,
            "is_collapsed": False
        },
        {
            "id": "clean.py",
            "label": "clean.py",
            "node_type": "file",
            "display_name": "数据清洗",
            "file_count": 1,
            "total_lines": 20,
            "importance_score": 0.85,
            "is_collapsed": False
        },
        {
            "id": "feature_eng.py",
            "label": "feature_eng.py",
            "node_type": "file",
            "display_name": "特征工程",
            "file_count": 1,
            "total_lines": 35,
            "importance_score": 0.9,
            "is_collapsed": False
        },
        {
            "id": "model_train.py",
            "label": "model_train.py",
            "node_type": "file",
            "display_name": "模型训练",
            "file_count": 1,
            "total_lines": 40,
            "importance_score": 0.95,
            "is_collapsed": False
        },
        {
            "id": "backtest.py",
            "label": "backtest.py",
            "node_type": "file",
            "display_name": "策略回测",
            "file_count": 1,
            "total_lines": 45,
            "importance_score": 0.9,
            "is_collapsed": False
        },
        {
            "id": "config/settings.py",
            "label": "settings.py",
            "node_type": "file",
            "display_name": "配置管理",
            "file_count": 1,
            "total_lines": 20,
            "importance_score": 0.6,
            "is_collapsed": False
        },
        {
            "id": "config/config.yaml",
            "label": "config.yaml",
            "node_type": "config",
            "display_name": "配置文件",
            "file_count": 1,
            "total_lines": 15,
            "importance_score": 0.5,
            "is_collapsed": False
        },
        {
            "id": "data/raw/AAPL_raw.csv",
            "label": "AAPL_raw.csv",
            "node_type": "data",
            "display_name": "原始数据",
            "file_count": 1,
            "total_lines": 0,
            "importance_score": 0.4,
            "is_collapsed": False
        },
        {
            "id": "data/clean/AAPL_clean.csv",
            "label": "AAPL_clean.csv",
            "node_type": "data",
            "display_name": "清洗后数据",
            "file_count": 1,
            "total_lines": 0,
            "importance_score": 0.4,
            "is_collapsed": False
        },
        {
            "id": "data/features/features.csv",
            "label": "features.csv",
            "node_type": "data",
            "display_name": "特征数据",
            "file_count": 1,
            "total_lines": 0,
            "importance_score": 0.5,
            "is_collapsed": False
        },
        {
            "id": "models/rf_model.pkl",
            "label": "rf_model.pkl",
            "node_type": "model",
            "display_name": "训练模型",
            "file_count": 1,
            "total_lines": 0,
            "importance_score": 0.7,
            "is_collapsed": False
        },
        {
            "id": "results/backtest_results.csv",
            "label": "backtest_results.csv",
            "node_type": "output",
            "display_name": "回测结果",
            "file_count": 1,
            "total_lines": 0,
            "importance_score": 0.6,
            "is_collapsed": False
        }
    ]
    
    links = [
        {
            "source": "main.py",
            "target": "data_fetch.py",
            "link_type": "control_flow",
            "label": "调用 fetch_stock_data()",
            "weight": 0.8
        },
        {
            "source": "data_fetch.py",
            "target": "data/raw/AAPL_raw.csv",
            "link_type": "data_flow",
            "label": "产出 AAPL_raw.csv",
            "weight": 1.5
        },
        {
            "source": "data/raw/AAPL_raw.csv",
            "target": "clean.py",
            "link_type": "data_flow",
            "label": "读取原始数据",
            "weight": 1.5
        },
        {
            "source": "clean.py",
            "target": "data/clean/AAPL_clean.csv",
            "link_type": "data_flow",
            "label": "产出清洗数据",
            "weight": 1.5
        },
        {
            "source": "data/clean/AAPL_clean.csv",
            "target": "feature_eng.py",
            "link_type": "data_flow",
            "label": "读取清洗数据",
            "weight": 1.5
        },
        {
            "source": "feature_eng.py",
            "target": "data/features/features.csv",
            "link_type": "data_flow",
            "label": "产出特征数据",
            "weight": 1.5
        },
        {
            "source": "data/features/features.csv",
            "target": "model_train.py",
            "link_type": "data_flow",
            "label": "读取特征数据",
            "weight": 1.5
        },
        {
            "source": "model_train.py",
            "target": "models/rf_model.pkl",
            "link_type": "data_flow",
            "label": "产出模型文件",
            "weight": 1.5
        },
        {
            "source": "model_train.py",
            "target": "results/feature_importance.csv",
            "link_type": "data_flow",
            "label": "产出特征重要性",
            "weight": 1.0
        },
        {
            "source": "backtest.py",
            "target": "model_train.py",
            "link_type": "control_flow",
            "label": "调用 load_model()",
            "weight": 0.8
        },
        {
            "source": "data/features/features.csv",
            "target": "backtest.py",
            "link_type": "data_flow",
            "label": "读取特征数据",
            "weight": 1.5
        },
        {
            "source": "models/rf_model.pkl",
            "target": "backtest.py",
            "link_type": "data_flow",
            "label": "加载模型",
            "weight": 1.0
        },
        {
            "source": "backtest.py",
            "target": "results/backtest_results.csv",
            "link_type": "data_flow",
            "label": "产出回测结果",
            "weight": 1.5
        },
        {
            "source": "data_fetch.py",
            "target": "config/settings.py",
            "link_type": "config_dependency",
            "label": "读取 API_KEY",
            "weight": 0.5
        },
        {
            "source": "config/settings.py",
            "target": "config/config.yaml",
            "link_type": "config_dependency",
            "label": "加载配置",
            "weight": 0.5
        }
    ]
    
    groups = [
        {
            "group_id": "group_data",
            "group_name": "数据处理",
            "nodes": ["data_fetch.py", "clean.py", "feature_eng.py"],
            "group_type": "functional_group"
        },
        {
            "group_id": "group_model",
            "group_name": "模型训练",
            "nodes": ["model_train.py", "backtest.py"],
            "group_type": "functional_group"
        },
        {
            "group_id": "group_config",
            "group_name": "配置管理",
            "nodes": ["config/settings.py", "config/config.yaml"],
            "group_type": "directory"
        }
    ]
    
    stages = [
        {
            "name": "数据采集",
            "files": ["data_fetch.py", "data/raw/AAPL_raw.csv"],
            "order": 1
        },
        {
            "name": "数据清洗",
            "files": ["clean.py", "data/clean/AAPL_clean.csv"],
            "order": 2
        },
        {
            "name": "特征工程",
            "files": ["feature_eng.py", "data/features/features.csv"],
            "order": 3
        },
        {
            "name": "模型训练",
            "files": ["model_train.py", "models/rf_model.pkl"],
            "order": 4
        },
        {
            "name": "策略回测",
            "files": ["backtest.py", "results/backtest_results.csv"],
            "order": 5
        }
    ]
    
    config = {
        "strategy": "stage_partition",
        "direction": "LR",
        "node_spacing": 60,
        "rank_spacing": 150,
        "stages": ["数据采集", "数据清洗", "特征工程", "模型训练", "策略回测"],
        "description": "按数据处理阶段分区布局"
    }
    
    statistics = {
        "total_files": 13,
        "total_lines": 230,
        "max_depth": 5,
        "by_type": {
            "data_flow": 10,
            "control_flow": 2,
            "config_dependency": 2
        }
    }
    
    return {
        "project_name": "量化策略项目",
        "project_description": "一个完整的量化交易策略开发流程",
        "generated_at": datetime.now().isoformat(),
        "nodes": nodes,
        "links": links,
        "groups": groups,
        "stages": stages,
        "config": config,
        "statistics": statistics
    }


if __name__ == "__main__":
    demo_data = generate_quant_project_demo()
    print(json.dumps(demo_data, indent=2, ensure_ascii=False))
