import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import sqlite3
import plotly.express as px
import plotly.graph_objects as go
from dash import Dash, dcc, html
from dash.dependencies import Input, Output
import warnings
warnings.filterwarnings('ignore')

class TransactionMonitor:
    def __init__(self, db_path='transaction_data.db'):
        """Initialize the monitoring system with database connection"""
        self.conn = sqlite3.connect(db_path)
        self.setup_database()
        
    def setup_database(self):
        """Create necessary tables if they don't exist"""
        cursor = self.conn.cursor()
        
        # Create transactions table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS transactions (
                transaction_id TEXT PRIMARY KEY,
                timestamp DATETIME,
                merchant_id TEXT,
                amount FLOAT,
                currency TEXT,
                card_type TEXT,
                response_code TEXT,
                processing_time FLOAT,
                error_code TEXT,
                region TEXT
            )
        ''')
        
        # Create SLA monitoring table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sla_metrics (
                date DATE,
                total_transactions INTEGER,
                avg_response_time FLOAT,
                error_rate FLOAT,
                sla_breaches INTEGER
            )
        ''')
        
        self.conn.commit()

    def load_sample_data(self):
        """Load real transaction data from CSV file"""
        # Note: In reality, you would connect to Mastercard's transaction database
        # This is using a sample dataset for demonstration
        df = pd.read_csv('transaction_sample.csv')
        df.to_sql('transactions', self.conn, if_exists='append', index=False)

    def validate_transaction(self, transaction):
        """
        Validate transaction data integrity
        Returns tuple of (is_valid, error_codes)
        """
        error_codes = []
        
        # Check for missing required fields
        required_fields = ['merchant_id', 'amount', 'currency', 'card_type']
        for field in required_fields:
            if pd.isna(transaction[field]):
                error_codes.append(f'MISSING_{field.upper()}')
        
        # Validate amount
        if transaction['amount'] <= 0:
            error_codes.append('INVALID_AMOUNT')
        
        # Validate currency code format (ISO 4217)
        if len(str(transaction['currency'])) != 3:
            error_codes.append('INVALID_CURRENCY')
            
        # Validate response time SLA (4 seconds)
        if transaction['processing_time'] > 4.0:
            error_codes.append('SLA_BREACH')
        
        return len(error_codes) == 0, error_codes

    def analyze_performance(self, start_date, end_date):
        """Analyze transaction performance metrics"""
        query = f"""
        SELECT 
            DATE(timestamp) as date,
            COUNT(*) as total_transactions,
            AVG(processing_time) as avg_response_time,
            SUM(CASE WHEN error_code IS NOT NULL THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as error_rate,
            SUM(CASE WHEN processing_time > 4.0 THEN 1 ELSE 0 END) as sla_breaches
        FROM transactions
        WHERE DATE(timestamp) BETWEEN '{start_date}' AND '{end_date}'
        GROUP BY DATE(timestamp)
        ORDER BY DATE(timestamp)
        """
        return pd.read_sql_query(query, self.conn)

    def generate_daily_report(self, date):
        """Generate daily performance report"""
        metrics = self.analyze_performance(date, date)
        if metrics.empty:
            return "No data available for specified date"
            
        report = f"""
        Data Integrity Daily Report - {date}
        =====================================
        
        Transaction Summary:
        - Total Transactions: {metrics['total_transactions'].iloc[0]:,}
        - Average Response Time: {metrics['avg_response_time'].iloc[0]:.2f}s
        - Error Rate: {metrics['error_rate'].iloc[0]:.2f}%
        - SLA Breaches: {metrics['sla_breaches'].iloc[0]:,}
        
        Performance Against SLA:
        - Response Time SLA (4s): {'✓ Met' if metrics['avg_response_time'].iloc[0] <= 4 else '✗ Not Met'}
        - Error Rate SLA (1%): {'✓ Met' if metrics['error_rate'].iloc[0] <= 1 else '✗ Not Met'}
        
        Action Items:
        {self.generate_action_items(metrics.iloc[0])}
        """
        return report

    def generate_action_items(self, metrics):
        """Generate action items based on performance metrics"""
        actions = []
        
        if metrics['avg_response_time'] > 4:
            actions.append("- URGENT: Investigate high response times - SLA breach detected")
            
        if metrics['error_rate'] > 1:
            actions.append("- Analyze error patterns and implement corrective measures")
            
        if metrics['sla_breaches'] > 0:
            actions.append(f"- Review {metrics['sla_breaches']} transactions exceeding response time SLA")
            
        return "\n".join(actions) if actions else "- No immediate actions required"

    def create_dashboard(self):
        """Create interactive monitoring dashboard"""
        app = Dash(__name__)
        
        app.layout = html.Div([
            html.H1("Transaction Data Integrity Monitor"),
            
            dcc.DatePickerRange(
                id='date-range',
                start_date=datetime.now().date() - timedelta(days=30),
                end_date=datetime.now().date(),
            ),
            
            dcc.Graph(id='transaction-volume'),
            dcc.Graph(id='error-rate'),
            dcc.Graph(id='response-time'),
            
            html.Div(id='sla-summary')
        ])
        
        @app.callback(
            [Output('transaction-volume', 'figure'),
             Output('error-rate', 'figure'),
             Output('response-time', 'figure'),
             Output('sla-summary', 'children')],
            [Input('date-range', 'start_date'),
             Input('date-range', 'end_date')]
        )
        def update_dashboard(start_date, end_date):
            metrics = self.analyze_performance(start_date, end_date)
            
            volume_fig = px.line(metrics, x='date', y='total_transactions',
                               title='Daily Transaction Volume')
            
            error_fig = px.line(metrics, x='date', y='error_rate',
                               title='Error Rate (%)')
            error_fig.add_hline(y=1, line_dash="dash", line_color="red",
                               annotation_text="SLA Threshold (1%)")
            
            response_fig = px.line(metrics, x='date', y='avg_response_time',
                                 title='Average Response Time (s)')
            response_fig.add_hline(y=4, line_dash="dash", line_color="red",
                                 annotation_text="SLA Threshold (4s)")
            
            sla_summary = html.Div([
                html.H3("SLA Summary"),
                html.P(f"Total SLA Breaches: {metrics['sla_breaches'].sum()}"),
                html.P(f"Average Error Rate: {metrics['error_rate'].mean():.2f}%"),
                html.P(f"Average Response Time: {metrics['avg_response_time'].mean():.2f}s")
            ])
            
            return volume_fig, error_fig, response_fig, sla_summary
        
        return app

def main():
    # Initialize monitoring system
    monitor = TransactionMonitor()
    
    # Generate daily report
    today = datetime.now().date()
    report = monitor.generate_daily_report(today)
    print(report)
    
    # Launch monitoring dashboard
    app = monitor.create_dashboard()
    app.run_server(debug=True)

if __name__ == "__main__":
    main()
