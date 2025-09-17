"""
Expiry Trade Generator - Streamlit Web Application
Automated Excel transformation for derivatives and cash trades with tax calculations

Features:
- Process futures and options trades at expiry
- Generate derivatives closing trades
- Create cash trades with STT and Stamp Duty calculations
- Handle index vs stock products differently
- Export to Excel/CSV formats
"""

import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import io
from typing import Tuple, List, Dict

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
    """
    Main processor class for expiry trades
    
    Processes derivatives and cash trades with tax calculations:
    - Futures: STT @ 0.1%, Stamp Duty @ 0.002%
    - Long Options: STT @ 0.125% of intrinsic, Stamp Duty @ 0.003% of strike
    - Short Options: No taxes
    """
    
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
    def is_index_product(underlying: str) -> bool:
        """Check if the underlying is an index product"""
        if pd.isna(underlying):
            return False
        return 'INDEX' in str(underlying).upper()
    
    @staticmethod
    def process_futures(row: pd.Series) -> Tuple[Dict, Dict]:
        """Process futures trades"""
        position = float(row['Position'])
        lot_size = float(row['Lot Size'])
        last_price = float(row['last price'])
        
        # Check if it's an index future
        is_index = ExpiryTradeProcessor.is_index_product(row['Underlying'])
        
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
            'Lot Size': lot_size,
            'tradenotes': ''  # Blank for futures
        }
        
        # Cash entry - only for stock futures (not index futures)
        cash = None
        if not is_index:
            cash_quantity = abs(position) * lot_size
            cash_price = last_price
            
            # Tax Calculations for Futures
            # STT = Quantity * Price * 0.1% (0.001)
            stt = cash_quantity * cash_price * 0.001
            
            # Stamp Duty = Quantity * Price * 0.002% (0.00002)
            stamp_duty = cash_quantity * cash_price * 0.00002
            
            # Total Taxes
            taxes = stt + stamp_duty
            
            cash = {
                'Underlying': row['Underlying'],
                'Symbol': row['Underlying'],  # For cash, Symbol = Underlying
                'Expiry': '',
                'Buy/Sell': 'Buy' if position > 0 else 'Sell',
                'Strategy': 'EQLO2',  # Always EQLO2 for all cash trades
                'Position': cash_quantity,
                'Price': cash_price,
                'Type': 'CASH',
                'Strike': '',
                'Lot Size': '',
                'STT': round(stt, 2),  # Round to 2 decimal places for currency
                'Stamp Duty': round(stamp_duty, 2),
                'Taxes': round(taxes, 2)
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
        
        # Determine ITM status and index/stock type
        is_itm = ExpiryTradeProcessor.determine_option_status(option_type, strike, last_price)
        is_index = ExpiryTradeProcessor.is_index_product(row['Underlying'])
        
        # Derivatives entry
        if option_type == 'Call':
            deriv_buy_sell = 'Sell' if position > 0 else 'Buy'
            deriv_strategy = 'FULO' if position > 0 else 'FUSH'
        else:  # Put
            deriv_buy_sell = 'Sell' if position > 0 else 'Buy'
            deriv_strategy = 'FUSH' if position > 0 else 'FULO'
        
        # Determine price for derivatives
        if is_index:
            # Index options are cash-settled at intrinsic value
            if is_itm:
                if option_type == 'Call':
                    deriv_price = max(0, last_price - strike)  # Intrinsic value for call (can't be negative)
                else:  # Put
                    deriv_price = max(0, strike - last_price)  # Intrinsic value for put (can't be negative)
            else:
                deriv_price = 0  # OTM expires worthless
        else:
            # Stock options always close at 0 (physical delivery)
            deriv_price = 0
        
        # Determine tradenotes (only for non-index ITM options)
        tradenotes = ''
        if is_itm and not is_index:
            if deriv_buy_sell == 'Buy':
                tradenotes = 'A'
            else:  # Sell
                tradenotes = 'E'
        
        derivative = {
            'Underlying': row['Underlying'],
            'Symbol': row['Symbol'],
            'Expiry': row['Expiry'],
            'Buy/Sell': deriv_buy_sell,
            'Strategy': deriv_strategy,
            'Position': abs(position),
            'Price': deriv_price,
            'Type': option_type,
            'Strike': strike,
            'Lot Size': lot_size,
            'tradenotes': tradenotes
        }
        
        # Cash entry - only for ITM single stock options (NOT for index)
        cash = None
        if is_itm and not is_index:
            cash_quantity = abs(position) * lot_size
            settlement_price = last_price  # Last price is the settlement/expiry price
            strike_price = strike  # Strike is the execution price for cash trade
            
            if option_type == 'Call':
                cash_buy_sell = 'Buy' if position > 0 else 'Sell'
                cash_price = strike_price
                intrinsic_value = settlement_price - strike_price
            else:  # Put
                cash_buy_sell = 'Sell' if position > 0 else 'Buy'
                cash_price = strike_price
                intrinsic_value = strike_price - settlement_price
            
            # Tax Calculations for Options
            # Only LONG options (original position > 0) pay taxes
            if position > 0:
                # STT for Long ITM Options = 0.125% of Intrinsic Value * Quantity
                # Ensure intrinsic value is non-negative for tax calculation
                stt = cash_quantity * max(0, intrinsic_value) * 0.00125
                
                # Stamp Duty for Long ITM Options = 0.003% of Strike Price * Quantity
                stamp_duty = cash_quantity * strike_price * 0.00003
            else:
                # Short ITM Options pay no taxes
                stt = 0
                stamp_duty = 0
            
            # Total Taxes
            taxes = stt + stamp_duty
            
            cash = {
                'Underlying': row['Underlying'],
                'Symbol': row['Underlying'],
                'Expiry': '',
                'Buy/Sell': cash_buy_sell,
                'Strategy': 'EQLO2',  # Always EQLO2 for all cash trades
                'Position': cash_quantity,
                'Price': cash_price,
                'Type': 'CASH',
                'Strike': '',
                'Lot Size': '',
                'STT': round(stt, 2),  # Round to 2 decimal places for currency
                'Stamp Duty': round(stamp_duty, 2),
                'Taxes': round(taxes, 2)
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
                    if cash:  # Cash might be None for index futures
                        cash_trades.append(cash)
                    
                elif trade_type in ['Call', 'Put']:
                    deriv, cash = ExpiryTradeProcessor.process_options(row)
                    derivatives.append(deriv)
                    if cash:  # Cash entry might be None for OTM options or index options
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
    st.markdown("**Automated Excel/CSV transformation for derivatives and cash trades with tax calculations**")
    
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
        1. **Derivatives**: Closing trades with tradenotes
           - Strategies: FULO (long unwind) / FUSH (short unwind)
           - Stock options: Close at 0
           - Index options: Close at intrinsic value
        2. **Cash**: Physical delivery trades with taxes
           - Strategy: EQLO2 (all trades)
           - Includes: STT, Stamp Duty, Total Taxes
           - No index products
        3. **Errors**: Processing issues
        """)
        
        with st.expander("✨ Key Features", expanded=True):
            st.markdown("""
            - ✅ **Automatic tax calculations** (STT & Stamp Duty)
            - ✅ **Smart differentiation** between Index & Stock products
            - ✅ **Physical delivery** processing for stocks
            - ✅ **Trade notes** (A/E) for option assignments
            - ✅ **Universal strategy** (EQLO2) for all cash trades
            - ✅ **Multi-format support** (Excel & CSV)
            """)
        
        st.divider()
        
        with st.expander("✨ Key Features", expanded=True):
            st.markdown("""
            - ✅ **Automatic tax calculations** (STT & Stamp Duty)
            - ✅ **Smart differentiation** between Index & Stock products
            - ✅ **Physical delivery** processing for stocks
            - ✅ **Trade notes** (A/E) for option assignments
            - ✅ **Universal strategy** (EQLO2) for all cash trades
            - ✅ **Multi-format support** (Excel & CSV)
            """)
        
        st.divider()
        
        st.success("""
        **📊 Key Features:**
        - ✅ Automatic tax calculations (STT & Stamp Duty)
        - ✅ Index vs Stock differentiation
        - ✅ Physical delivery processing
        - ✅ Trade note assignments (A/E)
        - ✅ Universal EQLO2 strategy for cash
        """)
        
        st.info("""
        **Derivatives Strategies:**
        - FULO: Long risk unwind
        - FUSH: Short risk unwind
        
        **Cash Strategy:**
        - EQLO2: All cash trades (universal)
        
        **Trade Notes (Stock Options Only):**
        - A: ITM stock option buy (assignment)
        - E: ITM stock option sell (exercise)
        - Blank: Futures/OTM/Index products
        
        **Tax Columns in Cash File:**
        - STT: Securities Transaction Tax
        - Stamp Duty: Transaction stamp duty
        - Taxes: Total (STT + Stamp Duty)
        
        **Index vs Stock Products:**
        - Index: Cash settled, no physical delivery
        - Stock: Physical delivery with taxes
        """)
        
        with st.expander("💰 Tax Calculation Details"):
            st.markdown("""
            ### Tax Rules for Cash Trades
            
            **📊 Stock Futures:**
            - **STT**: Position × Price × 0.1% (0.001)
            - **Stamp Duty**: Position × Price × 0.002% (0.00002)
            - Applied to both long and short futures
            
            **📈 Long ITM Stock Options (Original Position > 0):**
            - **STT**: Position × Intrinsic Value × 0.125% (0.00125)
              - Call Intrinsic = Last Price - Strike Price
              - Put Intrinsic = Strike Price - Last Price
            - **Stamp Duty**: Position × Strike Price × 0.003% (0.00003)
            
            **📉 Short ITM Stock Options (Original Position < 0):**
            - **STT**: ₹0 (No tax on short options)
            - **Stamp Duty**: ₹0 (No tax on short options)
            
            **🔢 Tax Calculation Examples:**
            
            1. **Long Future (100 lots × 500 lot size = 50,000 qty) @ ₹150:**
               - STT = 50,000 × 150 × 0.001 = ₹7,500
               - Stamp Duty = 50,000 × 150 × 0.00002 = ₹1.50
               - Total Tax = ₹7,501.50
            
            2. **Long ITM Call (50 lots × 250 lot size = 12,500 qty)**
               - Strike: ₹100, Settlement: ₹110
               - STT = 12,500 × (110-100) × 0.00125 = ₹156.25
               - Stamp Duty = 12,500 × 100 × 0.00003 = ₹37.50
               - Total Tax = ₹193.75
            
            3. **Short ITM Put:**
               - STT = ₹0
               - Stamp Duty = ₹0
               - Total Tax = ₹0
            
            **Note:** Index products don't appear in cash file (cash settled)
            """)
        
        with st.expander("🔧 Processing Rules"):
            st.markdown("""
            **Stock Futures:**
            - Derivatives: Close at Last Price (FULO/FUSH strategy)
            - Cash: Matching position (EQLO2 strategy)
            
            **Index Futures:**
            - Derivatives: Close at Last Price (FULO/FUSH strategy)
            - Cash: NO trade (cash settled)
            
            **Stock Options (Physical Delivery):**
            - Derivatives: Always close at Price = 0 (FULO/FUSH strategy)
            - ITM options: Add cash trade at strike (EQLO2 strategy)
            - OTM options: No cash trade
            - ITM options get tradenotes (A/E)
            
            **Index Options (Cash Settled):**
            - Derivatives ITM: Close at intrinsic value (FULO/FUSH strategy)
            - Derivatives OTM: Close at 0
            - Cash: NO trades (cash settled)
            - tradenotes: Always blank (no physical delivery)
            
            **Trade Notes Column:**
            - ITM Stock Buy trades: "A" (Assignment)
            - ITM Stock Sell trades: "E" (Exercise)
            - Index Options: Always blank
            - All Futures: Always blank
            - OTM Options: Always blank
            
            **Cash File Rules (Stocks Only):**
            - Stock Futures: Matching position at last price
            - ITM Stock Calls: Buy at Strike (long) / Sell at Strike (short)
            - ITM Stock Puts: Sell at Strike (long) / Buy at Strike (short)
            - **ALL trades use strategy: EQLO2**
            - Index products: NO cash entries
            
            **Tax Calculations in Cash File:**
            
            📊 **Futures Taxes:**
            - STT = Quantity × Price × 0.1%
            - Stamp Duty = Quantity × Price × 0.002%
            
            📈 **Long ITM Options (Position > 0):**
            - STT = Quantity × Intrinsic Value × 0.125%
              - Call Intrinsic = Settlement - Strike
              - Put Intrinsic = Strike - Settlement
            - Stamp Duty = Quantity × Strike × 0.003%
            
            📉 **Short ITM Options (Position < 0):**
            - STT = 0
            - Stamp Duty = 0
            
            💰 **Total Taxes = STT + Stamp Duty**
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
                    
                    # Count ITM options and index options
                    if not st.session_state['derivatives'].empty and 'tradenotes' in st.session_state['derivatives'].columns:
                        itm_count = len(st.session_state['derivatives'][st.session_state['derivatives']['tradenotes'].isin(['A', 'E'])])
                        # Count index options (those with intrinsic value pricing)
                        index_options = st.session_state['derivatives'][
                            (st.session_state['derivatives']['Type'].isin(['Call', 'Put'])) &
                            (st.session_state['derivatives']['Price'] != 0) &
                            (st.session_state['derivatives']['tradenotes'] == '')
                        ]
                        index_count = len(index_options)
                        
                        if itm_count > 0 or index_count > 0:
                            caption_parts = []
                            if itm_count > 0:
                                caption_parts.append(f"ITM Stock Options: {itm_count}")
                            if index_count > 0:
                                caption_parts.append(f"Index Options: {index_count}")
                            st.caption(" | ".join(caption_parts))
                    
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
                    
                    # Show total taxes if cash file exists
                    if not st.session_state['cash'].empty and 'Taxes' in st.session_state['cash'].columns:
                        total_tax = st.session_state['cash']['Taxes'].sum()
                        st.caption(f"Total Taxes: ₹{total_tax:,.2f}")
                    
                    if not st.session_state['cash'].empty:
                        excel_data = convert_df_to_excel(st.session_state['cash'])
                        st.download_button(
                            label="💰 Download Cash (with Taxes)",
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
                    st.info("✅ All files are ready for download using the buttons above")
                
                # Detailed views
                st.markdown("---")
                st.markdown("### 📋 Detailed Views")
                
                # Tabs for detailed data
                tab1, tab2, tab3 = st.tabs(["📈 Derivatives", "💰 Cash", "⚠️ Errors"])
                
                with tab1:
                    if not st.session_state['derivatives'].empty:
                        # Show summary statistics
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.markdown("**Strategy Distribution**")
                            strategy_counts = st.session_state['derivatives']['Strategy'].value_counts()
                            st.bar_chart(strategy_counts)
                        with col2:
                            st.markdown("**Buy/Sell Distribution**")
                            buysell_counts = st.session_state['derivatives']['Buy/Sell'].value_counts()
                            st.bar_chart(buysell_counts)
                        with col3:
                            st.markdown("**Trade Notes Distribution**")
                            if 'tradenotes' in st.session_state['derivatives'].columns:
                                tn_counts = st.session_state['derivatives']['tradenotes'].value_counts()
                                if len(tn_counts) > 0:
                                    # Create a more descriptive display
                                    tn_display = {}
                                    for key, value in tn_counts.items():
                                        if key == 'A':
                                            tn_display['A (Assignment)'] = value
                                        elif key == 'E':
                                            tn_display['E (Exercise)'] = value
                                        elif key == '':
                                            tn_display['Blank (Futures/OTM/Index)'] = value
                                    st.bar_chart(pd.Series(tn_display))
                                else:
                                    st.info("No ITM stock options")
                        
                        st.markdown("**Full Derivatives Data**")
                        # Display with proper column order including tradenotes
                        display_df = st.session_state['derivatives'][['Underlying', 'Symbol', 'Expiry', 'Buy/Sell', 
                                                                      'Strategy', 'Position', 'Price', 'Type', 
                                                                      'Strike', 'Lot Size', 'tradenotes']]
                        st.dataframe(
                            display_df,
                            use_container_width=True,
                            height=400
                        )
                    else:
                        st.info("No derivatives trades generated")
                
                with tab2:
                    if not st.session_state['cash'].empty:
                        # Show summary statistics
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.markdown("**Buy/Sell Distribution**")
                            buysell_counts = st.session_state['cash']['Buy/Sell'].value_counts()
                            st.bar_chart(buysell_counts)
                        with col2:
                            st.markdown("**Top Underlyings by Position**")
                            position_sum = st.session_state['cash'].groupby('Underlying')['Position'].sum().sort_values(ascending=False).head(10)
                            st.bar_chart(position_sum)
                        with col3:
                            st.markdown("**Tax Summary**")
                            if 'Taxes' in st.session_state['cash'].columns:
                                total_stt = st.session_state['cash']['STT'].sum()
                                total_stamp = st.session_state['cash']['Stamp Duty'].sum()
                                total_taxes = st.session_state['cash']['Taxes'].sum()
                                st.metric("Total STT", f"₹{total_stt:,.2f}")
                                st.metric("Total Stamp Duty", f"₹{total_stamp:,.2f}")
                                st.metric("Total Taxes", f"₹{total_taxes:,.2f}")
                        
                        # Note about strategy and taxes
                        col1, col2 = st.columns(2)
                        with col1:
                            st.success("✅ All cash trades use universal strategy: **EQLO2**")
                        with col2:
                            st.info("💰 Taxes calculated as per exchange rules for physical delivery")
                        
                        st.markdown("**Full Cash Data with Tax Details**")
                        # Display with proper column order including taxes
                        if 'STT' in st.session_state['cash'].columns:
                            display_columns = ['Underlying', 'Symbol', 'Expiry', 'Buy/Sell', 
                                             'Strategy', 'Position', 'Price', 'Type', 
                                             'Strike', 'Lot Size', 'STT', 'Stamp Duty', 'Taxes']
                            display_df = st.session_state['cash'][display_columns]
                        else:
                            display_df = st.session_state['cash']
                        
                        st.dataframe(
                            display_df,
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
            <p style='font-size: 18px; color: #555;'>Transform your expiry trades into derivatives and cash files with automated tax calculations!</p>
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
                <p>Automatically handles futures, stock options, and index options with proper settlement rules</p>
            </div>
            """, unsafe_allow_html=True)
        
        with col3:
            st.markdown("""
            <div style='background-color: #e8f5e9; padding: 20px; border-radius: 10px; height: 200px;'>
                <h4 style='color: #4caf50;'>3️⃣ Download</h4>
                <p>Get your files with proper formatting and automatic tax calculations</p>
            </div>
            """, unsafe_allow_html=True)
        
        # Sample data structure
        st.markdown("---")
        with st.expander("📋 View Sample Input Structure"):
            sample_data = pd.DataFrame({
                'Underlying': ['ABC IS Equity', 'XYZ IS Equity', 'PQR IS Equity', 'NIFTY INDEX', 'NIFTY INDEX', 'BANKNIFTY INDEX'],
                'Symbol': ['ABC=U5 IS Equity', 'XYZ IS 09/30/25 C100 Equity', 'PQR IS 09/30/25 P50 Equity', 'NIFTY=U5 Index', 'NIFTY 09/30/25 C25000 Index', 'BANKNIFTY 09/30/25 P48000 Index'],
                'Expiry': ['2025-09-30', '2025-09-30', '2025-09-30', '2025-09-30', '2025-09-30', '2025-09-30'],
                'Position': [100, -50, 75, -200, 40, -25],
                'Type': ['Futures', 'Call', 'Put', 'Futures', 'Call', 'Put'],
                'Strike': [np.nan, 100, 50, np.nan, 25000, 48000],
                'Lot Size': [500, 250, 300, 50, 50, 30],
                'last price': [150.5, 110.25, 45.75, 25500, 25250, 47800]
            })
            st.dataframe(sample_data, use_container_width=True)
            
            st.caption("""
            **Expected Output for Sample Data:**
            
            **Derivatives File:**
            - Row 1 (Stock Future): Close at 150.5, Strategy: FULO
            - Row 2 (Short ITM Call): Close at 0, Strategy: FUSH, Tradenote: A
            - Row 3 (Long OTM Put): Close at 0, Strategy: FUSH
            - Row 4 (Index Future): Close at 25500, Strategy: FUSH
            - Row 5 (Long ITM Index Call): Close at 250 (intrinsic)
            - Row 6 (Short ITM Index Put): Close at 200 (intrinsic)
            
            **Cash File (with Taxes):**
            - Row 1: Buy 50,000 @ 150.5 (EQLO2)
              - STT: ₹7,525 (0.1% of trade value)
              - Stamp Duty: ₹1.51 (0.002% of trade value)
            - Row 2: Buy 12,500 @ 100 (EQLO2)
              - STT: ₹0 (short option, no tax)
              - Stamp Duty: ₹0 (short option, no tax)
            - Row 3: No cash trade (OTM)
            - Rows 4-6: No cash trades (Index products)
            """)
            
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
