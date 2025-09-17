"""
Expiry Trade Generator - Streamlit Web Application
Automated Excel transformation for derivatives and cash trades
"""

import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import io
from typing import Tuple, List, Dict
# Note: No plotly import needed - using Streamlit's native charts

# Page configuration
st.set_page_config(
    page_title="Expiry Trade Generator",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for better UI - Professional light theme
st.markdown("""
<style>
    .main {
        padding-top: 2rem;
    }
    .stButton>button {
        width: 100%;
        border-radius: 5px;
        height: 3em;
        font-weight: 500;
    }
    .success-metric {
        background-color: #d4edda;
        border-left: 4px solid #28a745;
        padding: 12px;
        border-radius: 5px;
        margin: 10px 0;
    }
    .error-metric {
        background-color: #f8d7da;
        border-left: 4px solid #dc3545;
        padding: 12px;
        border-radius: 5px;
        margin: 10px 0;
    }
    .info-metric {
        background-color: #d1ecf1;
        border-left: 4px solid #17a2b8;
        padding: 12px;
        border-radius: 5px;
        margin: 10px 0;
    }
    .warning-metric {
        background-color: #fff3cd;
        border-left: 4px solid #ffc107;
        padding: 12px;
        border-radius: 5px;
        margin: 10px 0;
    }
    h1 {
        color: #2c3e50;
        font-weight: 600;
        border-bottom: 3px solid #3498db;
        padding-bottom: 10px;
    }
    h2 {
        color: #34495e;
        font-weight: 500;
    }
    h3 {
        color: #34495e;
        font-weight: 500;
    }
    .uploadedFile {
        border: 2px dashed #3498db !important;
        border-radius: 10px;
        padding: 20px;
        background-color: #f8f9fa;
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

def convert_df_to_excel(df: pd.DataFrame) -> bytes:
    """Convert dataframe to Excel bytes for download"""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Sheet1')
    return output.getvalue()

def convert_df_to_csv(df: pd.DataFrame) -> bytes:
    """Convert dataframe to CSV bytes for download"""
    return df.to_csv(index=False).encode('utf-8')

def main():
    # Header
    st.title("📊 Expiry Trade Generator")
    st.markdown("**Automated Excel/CSV transformation for derivatives and cash trades**")
    
    # Initialize session state
    if 'processed' not in st.session_state:
        st.session_state['processed'] = False
    
    # Sidebar for instructions
    with st.sidebar:
        st.header("📋 Instructions")
        st.markdown("""
        ### Input Requirements:
        **Excel (.xlsx, .xls) or CSV (.csv)** file with columns:
        - **Underlying**
        - **Symbol**
        - **Expiry**
        - **Position** (+ve = Long, -ve = Short)
        - **Type** (Futures/Call/Put)
        - **Strike** (for options)
        - **Lot Size**
        - **last price**
        
        ### Output Files:
        1. **Derivatives**: Closing trades
        2. **Cash**: Cash legs 
        3. **Errors**: Processing issues
        """)
        
        st.divider()
        
        st.info("""
        **Strategy Codes:**
        - FULO: Long risk unwind
        - FUSH: Short risk unwind
        - EQLO: Equity Long
        - EQSH: Equity Short
        """)
        
        with st.expander("🔧 Processing Rules"):
            st.markdown("""
            **Futures:**
            - Close at Last Price
            - Add matching cash trade
            
            **Options:**
            - Always close at Price = 0
            - ITM Single Stock: Add cash trade
            - OTM Options: No cash trade
            
            **ITM Cash Rules:**
            - Calls: Buy/Sell at Strike
            - Puts: Sell/Buy at Last Price
            """)
    
    # Main content area
    st.markdown("---")
    
    # File uploader section
    col1, col2, col3 = st.columns([1, 3, 1])
    with col2:
        uploaded_file = st.file_uploader(
            "Choose Excel/CSV File",
            type=['xlsx', 'xls', 'csv'],
            help="Upload your expiry trades file (Excel or CSV format)"
        )
    
    if uploaded_file is not None:
        try:
            # Read the file based on extension
            file_extension = uploaded_file.name.split('.')[-1].lower()
            
            if file_extension == 'csv':
                # Read CSV file
                df = pd.read_csv(uploaded_file)
            else:
                # Read Excel file (xls or xlsx)
                df = pd.read_excel(uploaded_file)
            
            # Display input summary
            st.markdown("### 📁 Input File Summary")
            
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Total Trades", len(df))
            with col2:
                if 'Type' in df.columns:
                    trade_types = df['Type'].value_counts()
                    st.metric("Futures", trade_types.get('Futures', 0))
                else:
                    st.metric("Futures", "N/A")
            with col3:
                if 'Type' in df.columns:
                    st.metric("Calls", trade_types.get('Call', 0))
                else:
                    st.metric("Calls", "N/A")
            with col4:
                if 'Type' in df.columns:
                    st.metric("Puts", trade_types.get('Put', 0))
                else:
                    st.metric("Puts", "N/A")
            
            # Show preview of input data
            with st.expander("👁️ Preview Input Data"):
                st.dataframe(df.head(20), use_container_width=True)
            
            # Process button
            st.markdown("---")
            col1, col2, col3 = st.columns([1, 2, 1])
            with col2:
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
                st.markdown("### 📊 Processing Results")
                
                # Results summary with download buttons
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    st.markdown('<div class="info-metric">', unsafe_allow_html=True)
                    st.markdown("**Derivatives File**")
                    st.metric("", f"{len(st.session_state['derivatives'])} trades", label_visibility="collapsed")
                    
                    if not st.session_state['derivatives'].empty:
                        excel_data = convert_df_to_excel(st.session_state['derivatives'])
                        st.download_button(
                            label="📥 Download Derivatives",
                            data=excel_data,
                            file_name='expiry_trades_derivatives.xlsx',
                            mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                            use_container_width=True
                        )
                    else:
                        st.warning("No derivatives generated")
                    st.markdown('</div>', unsafe_allow_html=True)
                
                with col2:
                    st.markdown('<div class="success-metric">', unsafe_allow_html=True)
                    st.markdown("**Cash File**")
                    st.metric("", f"{len(st.session_state['cash'])} cash legs", label_visibility="collapsed")
                    
                    if not st.session_state['cash'].empty:
                        excel_data = convert_df_to_excel(st.session_state['cash'])
                        st.download_button(
                            label="💰 Download Cash",
                            data=excel_data,
                            file_name='expiry_trades_cash.xlsx',
                            mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                            use_container_width=True
                        )
                    else:
                        st.warning("No cash trades generated")
                    st.markdown('</div>', unsafe_allow_html=True)
                
                with col3:
                    error_count = len(st.session_state['errors'])
                    if error_count > 0:
                        st.markdown('<div class="error-metric">', unsafe_allow_html=True)
                    else:
                        st.markdown('<div class="success-metric">', unsafe_allow_html=True)
                    
                    st.markdown("**Error Log**")
                    st.metric("", f"{error_count} errors", label_visibility="collapsed")
                    
                    if not st.session_state['errors'].empty:
                        csv_data = convert_df_to_csv(st.session_state['errors'])
                        st.download_button(
                            label="⚠️ Download Errors",
                            data=csv_data,
                            file_name='expiry_trades_errors.csv',
                            mime='text/csv',
                            use_container_width=True
                        )
                    else:
                        st.success("No errors!")
                    st.markdown('</div>', unsafe_allow_html=True)
                
                # Download all button
                st.markdown("---")
                col1, col2, col3 = st.columns([2, 3, 2])
                with col2:
                    # Create a ZIP file with all outputs (optional, complex implementation)
                    # For now, show success message with individual downloads above
                    st.info("✅ All files are ready for download using the buttons above")
                
                # Detailed views
                st.markdown("---")
                st.markdown("### 📋 Detailed Views")
                
                # Tabs for detailed data
                tab1, tab2, tab3 = st.tabs(["📈 Derivatives", "💰 Cash", "⚠️ Errors"])
                
                with tab1:
                    if not st.session_state['derivatives'].empty:
                        # Show summary statistics
                        col1, col2 = st.columns(2)
                        with col1:
                            st.markdown("**Strategy Distribution**")
                            strategy_counts = st.session_state['derivatives']['Strategy'].value_counts()
                            st.bar_chart(strategy_counts)
                        with col2:
                            st.markdown("**Buy/Sell Distribution**")
                            buysell_counts = st.session_state['derivatives']['Buy/Sell'].value_counts()
                            st.bar_chart(buysell_counts)
                        
                        st.markdown("**Full Derivatives Data**")
                        st.dataframe(
                            st.session_state['derivatives'],
                            use_container_width=True,
                            height=400
                        )
                    else:
                        st.info("No derivatives trades generated")
                
                with tab2:
                    if not st.session_state['cash'].empty:
                        # Show summary statistics
                        col1, col2 = st.columns(2)
                        with col1:
                            st.markdown("**Strategy Distribution**")
                            strategy_counts = st.session_state['cash']['Strategy'].value_counts()
                            st.bar_chart(strategy_counts)
                        with col2:
                            st.markdown("**Top Underlyings by Position**")
                            position_sum = st.session_state['cash'].groupby('Underlying')['Position'].sum().sort_values(ascending=False).head(10)
                            st.bar_chart(position_sum)
                        
                        st.markdown("**Full Cash Data**")
                        st.dataframe(
                            st.session_state['cash'],
                            use_container_width=True,
                            height=400
                        )
                    else:
                        st.info("No cash trades generated")
                
                with tab3:
                    if not st.session_state['errors'].empty:
                        st.error(f"Found {len(st.session_state['errors'])} errors during processing")
                        
                        # Show error details
                        st.markdown("**Error Details**")
                        st.dataframe(
                            st.session_state['errors'],
                            use_container_width=True,
                            height=400
                        )
                        
                        # Show each error as alert
                        with st.expander("View Individual Errors"):
                            for _, error in st.session_state['errors'].iterrows():
                                st.error(f"**Row {error['row_number']}** | {error['symbol']} | {error['reason']}")
                    else:
                        st.success("✅ All trades processed successfully with no errors!")
                
                # Reset button
                st.markdown("---")
                col1, col2, col3 = st.columns([2, 2, 2])
                with col2:
                    if st.button("🔄 Process New File", use_container_width=True):
                        st.session_state['processed'] = False
                        st.rerun()
        
        except Exception as e:
            st.error(f"Error processing file: {str(e)}")
            st.exception(e)
    
    else:
        # Landing page when no file is uploaded
        st.markdown("---")
        
        # Welcome message
        st.markdown("""
        <div style='background-color: #f0f2f6; padding: 30px; border-radius: 10px; text-align: center;'>
            <h2>Welcome to Expiry Trade Generator</h2>
            <p style='font-size: 18px; color: #555;'>Transform your expiry trades Excel/CSV file into derivatives and cash files with one click!</p>
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown("---")
        
        # How it works
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.markdown("""
            <div style='background-color: #e8f4fd; padding: 20px; border-radius: 10px; height: 200px;'>
                <h4 style='color: #0066cc;'>1️⃣ Upload</h4>
                <p>Upload your Excel or CSV file containing expiry trades data</p>
            </div>
            """, unsafe_allow_html=True)
        
        with col2:
            st.markdown("""
            <div style='background-color: #fff4e6; padding: 20px; border-radius: 10px; height: 200px;'>
                <h4 style='color: #ff9800;'>2️⃣ Process</h4>
                <p>Click process to automatically generate derivatives and cash trades</p>
            </div>
            """, unsafe_allow_html=True)
        
        with col3:
            st.markdown("""
            <div style='background-color: #e8f5e9; padding: 20px; border-radius: 10px; height: 200px;'>
                <h4 style='color: #4caf50;'>3️⃣ Download</h4>
                <p>Download your generated files with proper formatting</p>
            </div>
            """, unsafe_allow_html=True)
        
        # Sample data structure
        st.markdown("---")
        with st.expander("📋 View Sample Input Structure"):
            sample_data = pd.DataFrame({
                'Underlying': ['ABC IS Equity', 'XYZ IS Equity', 'PQR IS Equity', 'DEF IS Equity'],
                'Symbol': ['ABC=U5 IS Equity', 'XYZ IS 09/30/25 C100 Equity', 'PQR IS 09/30/25 P50 Equity', 'DEF=U5 IS Equity'],
                'Expiry': ['2025-09-30', '2025-09-30', '2025-09-30', '2025-09-30'],
                'Position': [100, -50, 75, -200],
                'Type': ['Futures', 'Call', 'Put', 'Futures'],
                'Strike': [np.nan, 100, 50, np.nan],
                'Lot Size': [500, 250, 300, 1000],
                'last price': [150.5, 110.25, 45.75, 225.80]
            })
            st.dataframe(sample_data, use_container_width=True)
            
            # Download sample files buttons
            col1, col2 = st.columns(2)
            with col1:
                sample_excel = convert_df_to_excel(sample_data)
                st.download_button(
                    label="📥 Download Sample Excel",
                    data=sample_excel,
                    file_name='sample_expiry_trades.xlsx',
                    mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                )
            with col2:
                sample_csv = convert_df_to_csv(sample_data)
                st.download_button(
                    label="📥 Download Sample CSV",
                    data=sample_csv,
                    file_name='sample_expiry_trades.csv',
                    mime='text/csv'
                )

if __name__ == "__main__":
    main()
