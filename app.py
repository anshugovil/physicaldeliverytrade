"""
Expiry Trade Generator - Streamlit Web Application
Automated Excel transformation for derivatives and cash trades
"""

import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import io
import base64
from typing import Tuple, List, Dict

# Page configuration
st.set_page_config(
    page_title="Expiry Trade Generator",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for better UI
st.markdown("""
<style>
    .stApp {
        background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
    }
    .main-header {
        font-size: 3rem;
        font-weight: bold;
        text-align: center;
        color: white;
        margin-bottom: 2rem;
        text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
    }
    .sub-header {
        font-size: 1.2rem;
        text-align: center;
        color: #f0f0f0;
        margin-bottom: 3rem;
    }
    .metric-card {
        background: white;
        padding: 1.5rem;
        border-radius: 10px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        margin: 1rem 0;
    }
    .success-box {
        background-color: #d4edda;
        border: 1px solid #c3e6cb;
        padding: 1rem;
        border-radius: 5px;
        color: #155724;
    }
    .error-box {
        background-color: #f8d7da;
        border: 1px solid #f5c6cb;
        padding: 1rem;
        border-radius: 5px;
        color: #721c24;
    }
    .info-box {
        background-color: #d1ecf1;
        border: 1px solid #bee5eb;
        padding: 1rem;
        border-radius: 5px;
        color: #0c5460;
    }
</style>
""", unsafe_allow_html=True)

class ExpiryTradeProcessor:
    """Main processor class for expiry trades"""
    
    @staticmethod
    def validate_row(row: pd.Series, row_index: int) -> Dict:
        """Validate a single row of data"""
        errors = []
        
        required_fields = ['Symbol', 'Type', 'Position', 'Lot Size', 'last price']
        for field in required_fields:
            if field not in row or pd.isna(row[field]):
                errors.append(f"Missing {field}")
        
        if errors:
            return {
                'valid': False,
                'error': {
                    'row_number': row_index + 2,  # +2 for Excel row number (1-indexed + header)
                    'symbol': row.get('Symbol', 'N/A'),
                    'underlying': row.get('Underlying', 'N/A'),
                    'reason': ', '.join(errors)
                }
            }
        
        return {'valid': True}
    
    @staticmethod
    def determine_option_status(option_type: str, strike: float, last_price: float) -> bool:
        """Determine if an option is ITM (In The Money)"""
        if option_type == 'Call':
            return last_price > strike
        elif option_type == 'Put':
            return last_price < strike
        return False
    
    @staticmethod
    def process_futures(row: pd.Series) -> Tuple[Dict, Dict]:
        """Process futures trades"""
        position = float(row['Position'])
        lot_size = float(row['Lot Size'])
        last_price = float(row['last price'])
        
        # Derivatives entry - close position
        derivative = {
            'Underlying': row['Underlying'],
            'Symbol': row['Symbol'],
            'Expiry': row['Expiry'],
            'Buy/Sell': 'Sell' if position > 0 else 'Buy',
            'Strategy': 'FULO' if position > 0 else 'FUSH',
            'Position': abs(position),
            'Price': last_price,
            'Type': row['Type'],
            'Strike': '',
            'Lot Size': lot_size
        }
        
        # Cash entry - open matching position
        cash = {
            'Underlying': row['Underlying'],
            'Symbol': row['Underlying'],  # For cash, Symbol = Underlying
            'Expiry': '',
            'Buy/Sell': 'Buy' if position > 0 else 'Sell',
            'Strategy': 'EQLO' if position > 0 else 'EQSH',
            'Position': abs(position) * lot_size,
            'Price': last_price,
            'Type': 'CASH',
            'Strike': '',
            'Lot Size': ''
        }
        
        return derivative, cash
    
    @staticmethod
    def process_options(row: pd.Series) -> Tuple[Dict, Dict]:
        """Process options trades (Calls and Puts)"""
        position = float(row['Position'])
        lot_size = float(row['Lot Size'])
        last_price = float(row['last price'])
        strike = float(row['Strike']) if pd.notna(row['Strike']) else 0
        option_type = row['Type']
        
        # Determine ITM status
        is_itm = ExpiryTradeProcessor.determine_option_status(option_type, strike, last_price)
        is_single_stock = 'INDEX' not in str(row['Underlying']).upper()
        
        # Derivatives entry - always close at 0
        if option_type == 'Call':
            deriv_buy_sell = 'Sell' if position > 0 else 'Buy'
            deriv_strategy = 'FULO' if position > 0 else 'FUSH'
        else:  # Put
            deriv_buy_sell = 'Sell' if position > 0 else 'Buy'
            deriv_strategy = 'FUSH' if position > 0 else 'FULO'
        
        derivative = {
            'Underlying': row['Underlying'],
            'Symbol': row['Symbol'],
            'Expiry': row['Expiry'],
            'Buy/Sell': deriv_buy_sell,
            'Strategy': deriv_strategy,
            'Position': abs(position),
            'Price': 0,
            'Type': option_type,
            'Strike': strike,
            'Lot Size': lot_size
        }
        
        # Cash entry - only for ITM options on single stocks
        cash = None
        if is_itm and is_single_stock:
            if option_type == 'Call':
                cash_buy_sell = 'Buy' if position > 0 else 'Sell'
                cash_strategy = 'EQLO' if position > 0 else 'EQSH'
                cash_price = strike
            else:  # Put
                cash_buy_sell = 'Sell' if position > 0 else 'Buy'
                cash_strategy = 'EQSH' if position > 0 else 'EQLO'
                cash_price = last_price
            
            cash = {
                'Underlying': row['Underlying'],
                'Symbol': row['Underlying'],
                'Expiry': '',
                'Buy/Sell': cash_buy_sell,
                'Strategy': cash_strategy,
                'Position': abs(position) * lot_size,
                'Price': cash_price,
                'Type': 'CASH',
                'Strike': '',
                'Lot Size': ''
            }
        
        return derivative, cash
    
    @staticmethod
    def process_dataframe(df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """Process the entire dataframe"""
        derivatives = []
        cash_trades = []
        errors = []
        
        for idx, row in df.iterrows():
            # Validate row
            validation = ExpiryTradeProcessor.validate_row(row, idx)
            if not validation['valid']:
                errors.append(validation['error'])
                continue
            
            try:
                trade_type = row['Type']
                
                if trade_type == 'Futures':
                    deriv, cash = ExpiryTradeProcessor.process_futures(row)
                    derivatives.append(deriv)
                    cash_trades.append(cash)
                    
                elif trade_type in ['Call', 'Put']:
                    deriv, cash = ExpiryTradeProcessor.process_options(row)
                    derivatives.append(deriv)
                    if cash:  # Cash entry might be None for OTM options
                        cash_trades.append(cash)
                        
                else:
                    errors.append({
                        'row_number': idx + 2,
                        'symbol': row.get('Symbol', 'N/A'),
                        'underlying': row.get('Underlying', 'N/A'),
                        'reason': f'Unknown Type: {trade_type}'
                    })
                    
            except Exception as e:
                errors.append({
                    'row_number': idx + 2,
                    'symbol': row.get('Symbol', 'N/A'),
                    'underlying': row.get('Underlying', 'N/A'),
                    'reason': f'Processing error: {str(e)}'
                })
        
        # Convert to DataFrames
        derivatives_df = pd.DataFrame(derivatives) if derivatives else pd.DataFrame()
        cash_df = pd.DataFrame(cash_trades) if cash_trades else pd.DataFrame()
        errors_df = pd.DataFrame(errors) if errors else pd.DataFrame()
        
        return derivatives_df, cash_df, errors_df

def download_link(df: pd.DataFrame, filename: str, file_type: str = 'xlsx') -> str:
    """Generate download link for dataframe"""
    if file_type == 'xlsx':
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Sheet1')
        excel_data = output.getvalue()
        b64 = base64.b64encode(excel_data).decode()
        return f'<a href="data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,{b64}" download="{filename}">📥 Download {filename}</a>'
    else:  # CSV
        csv = df.to_csv(index=False)
        b64 = base64.b64encode(csv.encode()).decode()
        return f'<a href="data:text/csv;base64,{b64}" download="{filename}">📥 Download {filename}</a>'

def main():
    # Header
    st.markdown('<h1 class="main-header">📊 Expiry Trade Generator</h1>', unsafe_allow_html=True)
    st.markdown('<p class="sub-header">Automated Excel transformation for derivatives and cash trades</p>', unsafe_allow_html=True)
    
    # Sidebar for instructions
    with st.sidebar:
        st.header("📋 Instructions")
        st.markdown("""
        ### Input Requirements:
        - **Excel file** with columns:
          - Underlying
          - Symbol
          - Expiry
          - Position
          - Type (Futures/Call/Put)
          - Strike (for options)
          - Lot Size
          - last price
        
        ### Position Signs:
        - **Positive** = Long position
        - **Negative** = Short position
        
        ### Output Files:
        1. **Derivatives**: Closing trades
        2. **Cash**: Cash legs for futures and ITM options
        3. **Errors**: Processing issues log
        
        ### Strategy Codes:
        - **FULO**: Long risk unwind
        - **FUSH**: Short risk unwind
        - **EQLO**: Equity Long
        - **EQSH**: Equity Short
        """)
        
        st.divider()
        
        # Processing rules in sidebar
        with st.expander("🔧 Processing Rules", expanded=False):
            st.markdown("""
            **Futures:**
            - Close at Last Price
            - Add matching cash trade
            
            **Options:**
            - Always close at Price = 0
            - ITM Single Stock Options: Add cash trade
            - OTM Options: No cash trade
            
            **Cash Trade Rules:**
            - ITM Calls: Buy/Sell at Strike
            - ITM Puts: Sell/Buy at Last Price
            """)
    
    # Main content area
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        # File uploader
        uploaded_file = st.file_uploader(
            "Upload Excel File",
            type=['xlsx', 'xls'],
            help="Select the expiry trades Excel file to process"
        )
    
    if uploaded_file is not None:
        try:
            # Read the Excel file
            df = pd.read_excel(uploaded_file)
            
            # Display input summary
            st.markdown("---")
            st.subheader("📁 Input File Summary")
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total Trades", len(df))
            with col2:
                trade_types = df['Type'].value_counts() if 'Type' in df.columns else pd.Series()
                st.metric("Trade Types", len(trade_types))
            with col3:
                st.metric("Columns", len(df.columns))
            
            # Show preview of input data
            with st.expander("👁️ Preview Input Data", expanded=False):
                st.dataframe(df.head(10), use_container_width=True)
            
            # Process button
            if st.button("🚀 Process Trades", type="primary", use_container_width=True):
                with st.spinner("Processing trades..."):
                    # Process the data
                    processor = ExpiryTradeProcessor()
                    derivatives_df, cash_df, errors_df = processor.process_dataframe(df)
                    
                    # Store in session state
                    st.session_state['derivatives'] = derivatives_df
                    st.session_state['cash'] = cash_df
                    st.session_state['errors'] = errors_df
                    st.session_state['processed'] = True
                
                st.success("✅ Processing complete!")
            
            # Display results if processed
            if st.session_state.get('processed', False):
                st.markdown("---")
                st.subheader("📊 Processing Results")
                
                # Results summary
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    st.markdown('<div class="metric-card">', unsafe_allow_html=True)
                    st.markdown("### Derivatives File")
                    st.metric("Trades Generated", len(st.session_state['derivatives']))
                    if not st.session_state['derivatives'].empty:
                        st.markdown(download_link(
                            st.session_state['derivatives'],
                            'expiry_trades_derivatives.xlsx',
                            'xlsx'
                        ), unsafe_allow_html=True)
                    st.markdown('</div>', unsafe_allow_html=True)
                
                with col2:
                    st.markdown('<div class="metric-card">', unsafe_allow_html=True)
                    st.markdown("### Cash File")
                    st.metric("Cash Legs Generated", len(st.session_state['cash']))
                    if not st.session_state['cash'].empty:
                        st.markdown(download_link(
                            st.session_state['cash'],
                            'expiry_trades_cash.xlsx',
                            'xlsx'
                        ), unsafe_allow_html=True)
                    st.markdown('</div>', unsafe_allow_html=True)
                
                with col3:
                    st.markdown('<div class="metric-card">', unsafe_allow_html=True)
                    st.markdown("### Error Log")
                    error_count = len(st.session_state['errors'])
                    st.metric("Errors Found", error_count)
                    if not st.session_state['errors'].empty:
                        st.markdown(download_link(
                            st.session_state['errors'],
                            'expiry_trades_errors.csv',
                            'csv'
                        ), unsafe_allow_html=True)
                    st.markdown('</div>', unsafe_allow_html=True)
                
                # Detailed views
                st.markdown("---")
                
                # Tabs for detailed data
                tab1, tab2, tab3 = st.tabs(["📈 Derivatives Details", "💰 Cash Details", "⚠️ Error Details"])
                
                with tab1:
                    if not st.session_state['derivatives'].empty:
                        st.dataframe(
                            st.session_state['derivatives'],
                            use_container_width=True,
                            height=400
                        )
                        
                        # Summary statistics
                        col1, col2 = st.columns(2)
                        with col1:
                            st.markdown("**Strategy Distribution:**")
                            strategy_counts = st.session_state['derivatives']['Strategy'].value_counts()
                            st.bar_chart(strategy_counts)
                        with col2:
                            st.markdown("**Buy/Sell Distribution:**")
                            buysell_counts = st.session_state['derivatives']['Buy/Sell'].value_counts()
                            st.bar_chart(buysell_counts)
                    else:
                        st.info("No derivatives trades generated")
                
                with tab2:
                    if not st.session_state['cash'].empty:
                        st.dataframe(
                            st.session_state['cash'],
                            use_container_width=True,
                            height=400
                        )
                        
                        # Summary statistics
                        col1, col2 = st.columns(2)
                        with col1:
                            st.markdown("**Strategy Distribution:**")
                            strategy_counts = st.session_state['cash']['Strategy'].value_counts()
                            st.bar_chart(strategy_counts)
                        with col2:
                            st.markdown("**Total Position by Underlying:**")
                            position_sum = st.session_state['cash'].groupby('Underlying')['Position'].sum().head(10)
                            st.bar_chart(position_sum)
                    else:
                        st.info("No cash trades generated")
                
                with tab3:
                    if not st.session_state['errors'].empty:
                        st.dataframe(
                            st.session_state['errors'],
                            use_container_width=True,
                            height=400
                        )
                        
                        # Error summary
                        st.markdown("**Error Summary:**")
                        for _, error in st.session_state['errors'].iterrows():
                            st.error(f"Row {error['row_number']}: {error['symbol']} - {error['reason']}")
                    else:
                        st.success("✅ No errors found - all trades processed successfully!")
                
                # Download all files button
                st.markdown("---")
                col1, col2, col3 = st.columns([1, 2, 1])
                with col2:
                    if st.button("📦 Download All Files", type="secondary", use_container_width=True):
                        st.markdown('<div class="success-box">', unsafe_allow_html=True)
                        st.markdown("### Download Links:")
                        
                        if not st.session_state['derivatives'].empty:
                            st.markdown(download_link(
                                st.session_state['derivatives'],
                                'expiry_trades_derivatives.xlsx',
                                'xlsx'
                            ), unsafe_allow_html=True)
                        
                        if not st.session_state['cash'].empty:
                            st.markdown(download_link(
                                st.session_state['cash'],
                                'expiry_trades_cash.xlsx',
                                'xlsx'
                            ), unsafe_allow_html=True)
                        
                        if not st.session_state['errors'].empty:
                            st.markdown(download_link(
                                st.session_state['errors'],
                                'expiry_trades_errors.csv',
                                'csv'
                            ), unsafe_allow_html=True)
                        
                        st.markdown('</div>', unsafe_allow_html=True)
        
        except Exception as e:
            st.error(f"Error processing file: {str(e)}")
            st.exception(e)
    
    else:
        # Landing page when no file is uploaded
        st.markdown("---")
        
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.markdown('<div class="info-box">', unsafe_allow_html=True)
            st.markdown("""
            ### 🚀 Getting Started
            
            1. **Prepare your Excel file** with the required columns
            2. **Upload the file** using the button above
            3. **Click Process** to generate output files
            4. **Download** the generated files
            
            The application will automatically:
            - Process futures and options trades
            - Generate derivative closing trades
            - Create cash legs for eligible trades
            - Log any processing errors
            """)
            st.markdown('</div>', unsafe_allow_html=True)
        
        # Sample data structure
        with st.expander("📋 Sample Input Structure"):
            sample_data = pd.DataFrame({
                'Underlying': ['ABC IS Equity', 'XYZ IS Equity', 'PQR IS Equity'],
                'Symbol': ['ABC=U5 IS Equity', 'XYZ IS 09/30/25 C100 Equity', 'PQR IS 09/30/25 P50 Equity'],
                'Expiry': ['2025-09-30', '2025-09-30', '2025-09-30'],
                'Position': [100, -50, 75],
                'Type': ['Futures', 'Call', 'Put'],
                'Strike': [np.nan, 100, 50],
                'Lot Size': [500, 250, 300],
                'last price': [150.5, 110.25, 45.75]
            })
            st.dataframe(sample_data, use_container_width=True)

if __name__ == "__main__":
    # Initialize session state
    if 'processed' not in st.session_state:
        st.session_state['processed'] = False
    
    main()