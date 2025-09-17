"""
Expiry Trade Generator - Streamlit Web Application
Automated Excel transformation for derivatives and cash trades with tax calculations
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
                    'row_number': row_index + 2,
                    'symbol': row.get('Symbol', 'N/A'),
                    'underlying': row.get('Underlying', 'N/A'),
                    'reason': ', '.join(errors)
                }
            }
        
        return {'valid': True}
    
    @staticmethod
    def determine_option_status(option_type: str, strike: float, last_price: float) -> bool:
        """Determine if an option is ITM"""
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
        
        is_index = ExpiryTradeProcessor.is_index_product(row['Underlying'])
        
        # Derivatives entry
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
            'tradenotes': ''
        }
        
        # Cash entry - only for stock futures
        cash = None
        if not is_index:
            cash_quantity = abs(position) * lot_size
            cash_price = last_price
            
            # Tax Calculations
            stt = cash_quantity * cash_price * 0.001
            stamp_duty = cash_quantity * cash_price * 0.00002
            taxes = stt + stamp_duty
            
            cash = {
                'Underlying': row['Underlying'],
                'Symbol': row['Underlying'],
                'Expiry': '',
                'Buy/Sell': 'Buy' if position > 0 else 'Sell',
                'Strategy': 'EQLO2',
                'Position': cash_quantity,
                'Price': cash_price,
                'Type': 'CASH',
                'Strike': '',
                'Lot Size': '',
                'tradenotes': '',  # Blank for futures
                'STT': round(stt, 2),
                'Stamp Duty': round(stamp_duty, 2),
                'Taxes': round(taxes, 2)
            }
        
        return derivative, cash
    
    @staticmethod
    def process_options(row: pd.Series) -> Tuple[Dict, Dict]:
        """Process options trades"""
        position = float(row['Position'])
        lot_size = float(row['Lot Size'])
        last_price = float(row['last price'])
        strike = float(row['Strike']) if pd.notna(row['Strike']) else 0
        option_type = row['Type']
        
        is_itm = ExpiryTradeProcessor.determine_option_status(option_type, strike, last_price)
        is_index = ExpiryTradeProcessor.is_index_product(row['Underlying'])
        
        # Derivatives entry
        if option_type == 'Call':
            deriv_buy_sell = 'Sell' if position > 0 else 'Buy'
            deriv_strategy = 'FULO' if position > 0 else 'FUSH'
        else:
            deriv_buy_sell = 'Sell' if position > 0 else 'Buy'
            deriv_strategy = 'FUSH' if position > 0 else 'FULO'
        
        # Determine price for derivatives
        if is_index:
            if is_itm:
                if option_type == 'Call':
                    deriv_price = max(0, last_price - strike)
                else:
                    deriv_price = max(0, strike - last_price)
            else:
                deriv_price = 0
        else:
            deriv_price = 0
        
        # Determine tradenotes for derivatives
        tradenotes = ''
        if is_itm and not is_index:
            if deriv_buy_sell == 'Buy':
                tradenotes = 'A'
            else:
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
        
        # Cash entry - only for ITM single stock options
        cash = None
        if is_itm and not is_index:
            cash_quantity = abs(position) * lot_size
            settlement_price = last_price
            strike_price = strike
            
            if option_type == 'Call':
                cash_buy_sell = 'Buy' if position > 0 else 'Sell'
                cash_price = strike_price
                intrinsic_value = settlement_price - strike_price
            else:
                cash_buy_sell = 'Sell' if position > 0 else 'Buy'
                cash_price = strike_price
                intrinsic_value = strike_price - settlement_price
            
            # Tax Calculations - only long options pay taxes
            if position > 0:
                stt = cash_quantity * max(0, intrinsic_value) * 0.00125
                stamp_duty = cash_quantity * strike_price * 0.00003
            else:
                stt = 0
                stamp_duty = 0
            
            taxes = stt + stamp_duty
            
            # Tradenotes based on original option position
            cash_tradenotes = 'E' if position > 0 else 'A'
            
            cash = {
                'Underlying': row['Underlying'],
                'Symbol': row['Underlying'],
                'Expiry': '',
                'Buy/Sell': cash_buy_sell,
                'Strategy': 'EQLO2',
                'Position': cash_quantity,
                'Price': cash_price,
                'Type': 'CASH',
                'Strike': '',
                'Lot Size': '',
                'tradenotes': cash_tradenotes,
                'STT': round(stt, 2),
                'Stamp Duty': round(stamp_duty, 2),
                'Taxes': round(taxes, 2)
            }
        
        return derivative, cash
    
    @staticmethod
    def generate_cash_summary(cash_df: pd.DataFrame) -> pd.DataFrame:
        """Generate cash summary with net deliverables"""
        if cash_df.empty:
            return pd.DataFrame()
        
        summary_rows = []
        
        # Variables for grand totals
        grand_total_consideration = 0
        grand_total_stt = 0
        grand_total_stamp = 0
        grand_total_taxes = 0
        
        # Group by underlying
        for underlying in cash_df['Underlying'].unique():
            underlying_trades = cash_df[cash_df['Underlying'] == underlying].copy()
            
            # Add trade rows
            for idx, trade in underlying_trades.iterrows():
                quantity = trade['Position']
                price = trade['Price']
                consideration = quantity * price if trade['Buy/Sell'] == 'Buy' else -quantity * price
                
                summary_rows.append({
                    'Underlying': underlying,
                    'Type': 'Trade',
                    'Buy/Sell': trade['Buy/Sell'],
                    'Quantity': quantity,
                    'Price': price,
                    'Consideration': round(consideration, 2),
                    'STT': trade.get('STT', 0),
                    'Stamp Duty': trade.get('Stamp Duty', 0),
                    'Taxes': trade.get('Taxes', 0)
                })
            
            # Calculate net deliverable
            buy_trades = underlying_trades[underlying_trades['Buy/Sell'] == 'Buy']
            sell_trades = underlying_trades[underlying_trades['Buy/Sell'] == 'Sell']
            
            buy_qty = buy_trades['Position'].sum() if not buy_trades.empty else 0
            sell_qty = sell_trades['Position'].sum() if not sell_trades.empty else 0
            net_qty = buy_qty - sell_qty
            
            buy_consideration = sum(row['Position'] * row['Price'] for _, row in buy_trades.iterrows()) if not buy_trades.empty else 0
            sell_consideration = sum(row['Position'] * row['Price'] for _, row in sell_trades.iterrows()) if not sell_trades.empty else 0
            net_consideration = buy_consideration - sell_consideration
            
            total_stt = underlying_trades['STT'].sum() if 'STT' in underlying_trades.columns else 0
            total_stamp = underlying_trades['Stamp Duty'].sum() if 'Stamp Duty' in underlying_trades.columns else 0
            total_taxes = underlying_trades['Taxes'].sum() if 'Taxes' in underlying_trades.columns else 0
            
            # Add to grand totals
            grand_total_consideration += net_consideration
            grand_total_stt += total_stt
            grand_total_stamp += total_stamp
            grand_total_taxes += total_taxes
            
            # Add NET DELIVERABLE row
            summary_rows.append({
                'Underlying': underlying,
                'Type': 'NET DELIVERABLE',
                'Buy/Sell': 'NET',
                'Quantity': net_qty,
                'Price': '',
                'Consideration': round(net_consideration, 2),
                'STT': round(total_stt, 2),
                'Stamp Duty': round(total_stamp, 2),
                'Taxes': round(total_taxes, 2)
            })
            
            # Add blank row for separation
            if underlying != cash_df['Underlying'].unique()[-1]:
                summary_rows.append({
                    'Underlying': '',
                    'Type': '',
                    'Buy/Sell': '',
                    'Quantity': '',
                    'Price': '',
                    'Consideration': '',
                    'STT': '',
                    'Stamp Duty': '',
                    'Taxes': ''
                })
        
        # Add separator
        summary_rows.append({
            'Underlying': '---',
            'Type': '---',
            'Buy/Sell': '---',
            'Quantity': '---',
            'Price': '---',
            'Consideration': '---',
            'STT': '---',
            'Stamp Duty': '---',
            'Taxes': '---'
        })
        
        # Add GRAND TOTAL row
        summary_rows.append({
            'Underlying': 'GRAND TOTAL',
            'Type': 'ALL POSITIONS',
            'Buy/Sell': '',
            'Quantity': '',
            'Price': '',
            'Consideration': round(grand_total_consideration, 2),
            'STT': round(grand_total_stt, 2),
            'Stamp Duty': round(grand_total_stamp, 2),
            'Taxes': round(grand_total_taxes, 2)
        })
        
        return pd.DataFrame(summary_rows)
    
    @staticmethod
    def process_dataframe(df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """Process the entire dataframe"""
        derivatives = []
        cash_trades = []
        errors = []
        
        for idx, row in df.iterrows():
            validation = ExpiryTradeProcessor.validate_row(row, idx)
            if not validation['valid']:
                errors.append(validation['error'])
                continue
            
            try:
                trade_type = row['Type']
                
                if trade_type == 'Futures':
                    deriv, cash = ExpiryTradeProcessor.process_futures(row)
                    derivatives.append(deriv)
                    if cash:
                        cash_trades.append(cash)
                
                elif trade_type in ['Call', 'Put']:
                    deriv, cash = ExpiryTradeProcessor.process_options(row)
                    derivatives.append(deriv)
                    if cash:
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
        
        derivatives_df = pd.DataFrame(derivatives) if derivatives else pd.DataFrame()
        cash_df = pd.DataFrame(cash_trades) if cash_trades else pd.DataFrame()
        errors_df = pd.DataFrame(errors) if errors else pd.DataFrame()
        cash_summary_df = ExpiryTradeProcessor.generate_cash_summary(cash_df)
        
        return derivatives_df, cash_df, cash_summary_df, errors_df

def convert_df_to_excel(df: pd.DataFrame) -> bytes:
    """Convert dataframe to Excel bytes"""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Sheet1')
    return output.getvalue()

def convert_df_to_csv(df: pd.DataFrame) -> bytes:
    """Convert dataframe to CSV bytes"""
    return df.to_csv(index=False).encode('utf-8')

def main():
    st.title("📊 Expiry Trade Generator")
    st.markdown("**Automated Excel/CSV transformation for derivatives and cash trades with tax calculations**")
    
    # Initialize session state
    if 'processed' not in st.session_state:
        st.session_state['processed'] = False
    
    # Sidebar
    with st.sidebar:
        st.header("📋 Instructions")
        st.markdown("""
        ### Input Requirements:
        **Excel or CSV file with columns:**
        - Underlying
        - Symbol
        - Expiry
        - Position (+ve = Long, -ve = Short)
        - Type (Futures/Call/Put)
        - Strike (for options)
        - Lot Size
        - last price
        
        ### Output Files:
        1. **Derivatives**: Closing trades with tradenotes
        2. **Cash**: Physical delivery with taxes and tradenotes
        3. **Cash Summary**: Net deliverables with grand total
        4. **Errors**: Processing issues
        """)
        
        st.info("""
        **Trade Notes:**
        - Derivatives: A=Assignment, E=Exercise
        - Cash: E=Long options exercised, A=Short options assigned
        
        **Tax Rules:**
        - Futures: STT 0.1%, Stamp 0.002%
        - Long Options: STT 0.125% of intrinsic, Stamp 0.003% of strike
        - Short Options: No taxes
        """)
    
    # Main content
    uploaded_file = st.file_uploader(
        "Choose Excel/CSV File",
        type=['xlsx', 'xls', 'csv'],
        help="Upload your expiry trades file"
    )
    
    if uploaded_file is not None:
        try:
            # Read file
            file_extension = uploaded_file.name.split('.')[-1].lower()
            if file_extension == 'csv':
                df = pd.read_csv(uploaded_file)
            else:
                df = pd.read_excel(uploaded_file)
            
            # Display summary
            st.markdown("### 📁 Input File Summary")
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Total Trades", len(df))
            with col2:
                if 'Type' in df.columns:
                    st.metric("Futures", df[df['Type'] == 'Futures'].shape[0])
                else:
                    st.metric("Futures", "N/A")
            with col3:
                if 'Type' in df.columns:
                    st.metric("Calls", df[df['Type'] == 'Call'].shape[0])
                else:
                    st.metric("Calls", "N/A")
            with col4:
                if 'Type' in df.columns:
                    st.metric("Puts", df[df['Type'] == 'Put'].shape[0])
                else:
                    st.metric("Puts", "N/A")
            
            with st.expander("Preview Input Data"):
                st.dataframe(df.head(20))
            
            # Process button
            if st.button("🚀 Process Trades", type="primary"):
                with st.spinner("Processing..."):
                    processor = ExpiryTradeProcessor()
                    derivatives_df, cash_df, cash_summary_df, errors_df = processor.process_dataframe(df)
                    
                    st.session_state['derivatives'] = derivatives_df
                    st.session_state['cash'] = cash_df
                    st.session_state['cash_summary'] = cash_summary_df
                    st.session_state['errors'] = errors_df
                    st.session_state['processed'] = True
                
                st.success("✅ Processing complete!")
            
            # Display results
            if st.session_state.get('processed', False):
                st.markdown("### 📊 Processing Results")
                
                # Download buttons
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    st.markdown("**Derivatives File**")
                    st.metric("Trades", len(st.session_state['derivatives']))
                    if not st.session_state['derivatives'].empty:
                        excel_data = convert_df_to_excel(st.session_state['derivatives'])
                        st.download_button(
                            "📥 Download",
                            data=excel_data,
                            file_name='expiry_trades_derivatives.xlsx',
                            mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                        )
                
                with col2:
                    st.markdown("**Cash File**")
                    st.metric("Trades", len(st.session_state['cash']))
                    if not st.session_state['cash'].empty:
                        excel_data = convert_df_to_excel(st.session_state['cash'])
                        st.download_button(
                            "💰 Download",
                            data=excel_data,
                            file_name='expiry_trades_cash.xlsx',
                            mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                        )
                
                with col3:
                    st.markdown("**Cash Summary**")
                    st.metric("Rows", len(st.session_state['cash_summary']))
                    if not st.session_state['cash_summary'].empty:
                        excel_data = convert_df_to_excel(st.session_state['cash_summary'])
                        st.download_button(
                            "📋 Download",
                            data=excel_data,
                            file_name='expiry_trades_cash_summary.xlsx',
                            mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                        )
                
                with col4:
                    st.markdown("**Error Log**")
                    st.metric("Errors", len(st.session_state['errors']))
                    if not st.session_state['errors'].empty:
                        csv_data = convert_df_to_csv(st.session_state['errors'])
                        st.download_button(
                            "⚠️ Download",
                            data=csv_data,
                            file_name='expiry_trades_errors.csv',
                            mime='text/csv'
                        )
                
                # Detailed views
                st.markdown("### 📋 Detailed Views")
                tabs = st.tabs(["📈 Derivatives", "💰 Cash", "📋 Summary", "⚠️ Errors"])
                
                with tabs[0]:
                    if not st.session_state['derivatives'].empty:
                        st.dataframe(st.session_state['derivatives'], use_container_width=True)
                    else:
                        st.info("No derivatives trades generated")
                
                with tabs[1]:
                    if not st.session_state['cash'].empty:
                        st.info("Trade Notes: E=Exercise (long options), A=Assignment (short options), Blank=Futures")
                        st.dataframe(st.session_state['cash'], use_container_width=True)
                    else:
                        st.info("No cash trades generated")
                
                with tabs[2]:
                    if not st.session_state['cash_summary'].empty:
                        # Highlight NET DELIVERABLE and GRAND TOTAL rows
                        def highlight_rows(row):
                            if 'NET DELIVERABLE' in str(row['Type']) or 'GRAND TOTAL' in str(row['Underlying']):
                                return ['font-weight: bold; background-color: lightblue'] * len(row)
                            return [''] * len(row)
                        
                        styled_df = st.session_state['cash_summary'].style.apply(highlight_rows, axis=1)
                        st.dataframe(styled_df, use_container_width=True)
                    else:
                        st.info("No cash summary generated")
                
                with tabs[3]:
                    if not st.session_state['errors'].empty:
                        st.dataframe(st.session_state['errors'], use_container_width=True)
                    else:
                        st.success("No errors!")
                
                if st.button("🔄 Process New File"):
                    st.session_state['processed'] = False
                    st.rerun()
        
        except Exception as e:
            st.error(f"Error processing file: {str(e)}")
    
    else:
        # Landing page
        st.markdown("""
        ### Welcome to Expiry Trade Generator
        
        This tool processes expiry trades and generates:
        1. **Derivatives file** - Closing trades with strategies
        2. **Cash file** - Physical delivery with taxes and tradenotes
        3. **Cash Summary** - Net deliverables by underlying with grand total
        4. **Error log** - Processing issues
        
        Upload your Excel or CSV file to get started!
        """)

if __name__ == "__main__":
    main()
