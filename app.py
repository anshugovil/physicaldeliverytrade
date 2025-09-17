"""
Portfolio Synthetic Call Transformer
A Streamlit application for transforming portfolio positions into synthetic calls
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime

# Page configuration
st.set_page_config(
    page_title="Portfolio Synthetic Call Transformer",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for better styling
st.markdown("""
    <style>
    .main {
        padding: 0rem 1rem;
    }
    .stButton>button {
        background-color: #4CAF50;
        color: white;
        border-radius: 5px;
        padding: 0.5rem 1rem;
        border: none;
        transition: 0.3s;
    }
    .stButton>button:hover {
        background-color: #45a049;
    }
    .success-box {
        padding: 1rem;
        border-radius: 0.5rem;
        background-color: #d4edda;
        border: 1px solid #c3e6cb;
        color: #155724;
        margin: 1rem 0;
    }
    .info-box {
        padding: 1rem;
        border-radius: 0.5rem;
        background-color: #d1ecf1;
        border: 1px solid #bee5eb;
        color: #0c5460;
        margin: 1rem 0;
    }
    .warning-box {
        padding: 1rem;
        border-radius: 0.5rem;
        background-color: #fff3cd;
        border: 1px solid #ffeaa7;
        color: #856404;
        margin: 1rem 0;
    }
    </style>
    """, unsafe_allow_html=True)

def load_sample_data():
    """Create sample data for demonstration"""
    data = {
        'Instrument': ['Futures', 'Cash', 'Puts', 'Puts', 'Puts', 'Puts', 'Puts', 'Calls', 'Calls', 'Calls'],
        'Position': [100000, 200000, 5000, 10000, 100000, 100000, 100000, 100000, 11000, 11000],
        'Strike': [None, None, 1240, 1230, 1200, 1150, 1100, 1200, 1250, 1150],
        'Market price': [1191, 1190, 60, 65, 25, 8, 4, 12, 4, 62]
    }
    df = pd.DataFrame(data)
    return df

def process_portfolio(df):
    """
    Process the portfolio to create synthetic calls
    """
    # Clean column names - remove leading/trailing spaces
    df.columns = df.columns.str.strip()
    
    # Check required columns
    required_columns = ['Instrument', 'Position', 'Strike', 'Market price']
    missing_columns = [col for col in required_columns if col not in df.columns]
    
    if missing_columns:
        st.error(f"Missing required columns: {missing_columns}")
        st.info(f"Found columns: {df.columns.tolist()}")
        return None, None, None
    
    # Standardize instrument names
    df['Instrument'] = df['Instrument'].str.strip().str.lower()
    
    # Separate instruments by type
    futures = df[df['Instrument'] == 'futures'].copy()
    cash = df[df['Instrument'] == 'cash'].copy()
    puts = df[df['Instrument'].str.contains('put', case=False)].copy()
    calls = df[df['Instrument'].str.contains('call', case=False)].copy()
    
    # Get underlying price (use futures price if available, otherwise cash)
    if not futures.empty:
        underlying_price = futures['Market price'].iloc[0]
    elif not cash.empty:
        underlying_price = cash['Market price'].iloc[0]
    else:
        st.error("No underlying price found (need Futures or Cash position)")
        return None, None, None
    
    # Calculate total stock positions
    total_futures = futures['Position'].sum() if not futures.empty else 0
    total_cash = cash['Position'].sum() if not cash.empty else 0
    
    # Sort puts by strike (highest first) - handle NaN values
    if not puts.empty:
        puts_sorted = puts.sort_values('Strike', ascending=False, na_position='last').copy()
    else:
        puts_sorted = puts.copy()
    
    # Initialize transformation tracking
    synthetic_calls = []
    transformation_log = []
    
    remaining_futures = total_futures
    remaining_cash = total_cash
    
    # Process puts by strike (highest to lowest)
    for strike in puts_sorted['Strike'].unique():
        if pd.isna(strike):
            continue
            
        puts_at_strike = puts_sorted[puts_sorted['Strike'] == strike].copy()
        
        for _, put_row in puts_at_strike.iterrows():
            puts_to_process = put_row['Position']
            put_market_price = put_row['Market price']
            
            while puts_to_process > 0 and (remaining_futures > 0 or remaining_cash > 0):
                # Determine how much to process
                if remaining_futures > 0:
                    process_amount = min(puts_to_process, remaining_futures)
                    remaining_futures -= process_amount
                    source = 'Futures'
                else:
                    process_amount = min(puts_to_process, remaining_cash)
                    remaining_cash -= process_amount
                    source = 'Cash'
                
                puts_to_process -= process_amount
                
                # Calculate synthetic call value
                synthetic_value = put_market_price + (underlying_price - strike)
                
                # Record the synthetic call
                synthetic_calls.append({
                    'Type': 'Synthetic Call',
                    'Strike': strike,
                    'Position': process_amount,
                    'Value per Unit': synthetic_value,
                    'Total Value': process_amount * synthetic_value,
                    'Created From': f'{source} + Put@{strike}'
                })
                
                # Log the transformation
                transformation_log.append({
                    'Step': len(transformation_log) + 1,
                    'Action': f'Create Synthetic Call',
                    'Source': source,
                    'Amount': process_amount,
                    'Put Strike': strike,
                    'Put Price': put_market_price,
                    'Synthetic Value': synthetic_value
                })
            
            # Record remaining puts if any
            if puts_to_process > 0:
                transformation_log.append({
                    'Step': len(transformation_log) + 1,
                    'Action': 'Unmatched Puts',
                    'Source': 'Puts',
                    'Amount': puts_to_process,
                    'Put Strike': strike,
                    'Put Price': put_market_price,
                    'Synthetic Value': 'N/A'
                })
    
    # Create final portfolio summary
    final_portfolio = []
    
    # Add remaining stock positions
    if remaining_futures > 0:
        final_portfolio.append({
            'Type': 'Futures',
            'Strike': None,
            'Position': remaining_futures,
            'Value per Unit': underlying_price,
            'Total Value': remaining_futures * underlying_price,
            'Risk Type': 'Long Stock'
        })
    
    if remaining_cash > 0:
        final_portfolio.append({
            'Type': 'Cash',
            'Strike': None,
            'Position': remaining_cash,
            'Value per Unit': underlying_price,
            'Total Value': remaining_cash * underlying_price,
            'Risk Type': 'Long Stock'
        })
    
    # Add synthetic calls
    for sc in synthetic_calls:
        final_portfolio.append({
            'Type': sc['Type'],
            'Strike': sc['Strike'],
            'Position': sc['Position'],
            'Value per Unit': sc['Value per Unit'],
            'Total Value': sc['Total Value'],
            'Risk Type': 'Call-like'
        })
    
    # Add original calls
    for _, call_row in calls.iterrows():
        final_portfolio.append({
            'Type': 'Original Call',
            'Strike': call_row['Strike'],
            'Position': call_row['Position'],
            'Value per Unit': call_row['Market price'],
            'Total Value': call_row['Position'] * call_row['Market price'],
            'Risk Type': 'Call-like'
        })
    
    # Check for unmatched puts
    total_puts = puts['Position'].sum() if not puts.empty else 0
    matched_puts = total_futures + total_cash - remaining_futures - remaining_cash
    unmatched_puts = total_puts - matched_puts
    
    if unmatched_puts > 0:
        # Add remaining puts to final portfolio
        remaining_puts_df = puts_sorted.copy()
        # Complex logic to identify which specific puts remain unmatched
        # This is simplified for now
        for _, put_row in remaining_puts_df.iterrows():
            if unmatched_puts <= 0:
                break
            position = min(put_row['Position'], unmatched_puts)
            if position > 0:
                final_portfolio.append({
                    'Type': 'Unmatched Put',
                    'Strike': put_row['Strike'],
                    'Position': position,
                    'Value per Unit': put_row['Market price'],
                    'Total Value': position * put_row['Market price'],
                    'Risk Type': 'Put Protection'
                })
                unmatched_puts -= position
    
    return pd.DataFrame(final_portfolio), pd.DataFrame(transformation_log), underlying_price

def create_risk_visualization(final_portfolio_df):
    """Create risk visualization charts"""
    
    # Group by Risk Type
    risk_summary = final_portfolio_df.groupby('Risk Type')['Total Value'].sum().reset_index()
    
    # Create pie chart
    fig_pie = px.pie(risk_summary, values='Total Value', names='Risk Type',
                      title='Portfolio Risk Distribution',
                      color_discrete_map={'Long Stock': '#2E86AB', 
                                         'Call-like': '#A23B72', 
                                         'Put Protection': '#F18F01'})
    
    # Create bar chart by instrument type
    type_summary = final_portfolio_df.groupby('Type')['Total Value'].sum().reset_index()
    fig_bar = px.bar(type_summary, x='Type', y='Total Value',
                      title='Portfolio Value by Instrument Type',
                      color='Type',
                      color_discrete_sequence=px.colors.qualitative.Set3)
    
    return fig_pie, fig_bar

def main():
    st.title("🎯 Portfolio Synthetic Call Transformer")
    st.markdown("Transform your portfolio positions into a standardized risk view using synthetic calls")
    
    # Sidebar
    with st.sidebar:
        st.header("📋 Instructions")
        st.markdown("""
        ### How it works:
        1. **Upload** your portfolio CSV file
        2. **Review** the transformation process
        3. **Analyze** the final risk position
        
        ### CSV Format Required:
        - `Instrument`: Type (Cash, Futures, Puts, Calls)
        - `Position`: Number of units
        - `Strike`: Strike price (for options)
        - `Market price`: Current market price
        
        ### Algorithm:
        1. Uses Futures first, then Cash
        2. Starts with highest strike puts
        3. Creates synthetic calls using:
           - Put Value + (Stock - Strike)
        """)
        
        st.divider()
        
        if st.button("📊 Load Sample Data"):
            st.session_state['data'] = load_sample_data()
            st.success("Sample data loaded!")
    
    # Main content area
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.header("📁 Data Input")
        
        uploaded_file = st.file_uploader(
            "Upload your portfolio CSV file",
            type=['csv'],
            help="File should contain Instrument, Position, Strike, and Market price columns"
        )
        
        if uploaded_file is not None:
            try:
                df = pd.read_csv(uploaded_file)
                # Clean column names
                df.columns = df.columns.str.strip()
                st.session_state['data'] = df
                st.success(f"✅ File loaded successfully! {len(df)} positions found.")
                
                # Show column info for debugging
                st.info(f"Columns detected: {', '.join(df.columns.tolist())}")
            except Exception as e:
                st.error(f"Error reading file: {str(e)}")
    
    with col2:
        st.header("📊 Current Portfolio")
        
        if 'data' in st.session_state:
            st.dataframe(st.session_state['data'], use_container_width=True)
        else:
            st.info("Please upload a file or load sample data from the sidebar")
    
    # Process button
    if 'data' in st.session_state:
        st.divider()
        
        if st.button("🔄 Transform Portfolio", type="primary", use_container_width=True):
            with st.spinner("Processing portfolio transformation..."):
                try:
                    final_portfolio, transformation_log, underlying_price = process_portfolio(st.session_state['data'])
                    
                    if final_portfolio is not None:
                        st.session_state['final_portfolio'] = final_portfolio
                        st.session_state['transformation_log'] = transformation_log
                        st.session_state['underlying_price'] = underlying_price
                        st.success("✅ Portfolio transformation complete!")
                except Exception as e:
                    st.error(f"Error during transformation: {str(e)}")
                    st.info("Please check that your CSV has the correct format with columns: Instrument, Position, Strike, Market price")
    
    # Display results
    if 'final_portfolio' in st.session_state:
        st.divider()
        st.header("📈 Transformation Results")
        
        # Display underlying price
        st.markdown(f"<div class='info-box'>📍 <b>Underlying Price Used:</b> {st.session_state['underlying_price']:.2f}</div>", 
                   unsafe_allow_html=True)
        
        # Create tabs for different views
        tab1, tab2, tab3, tab4 = st.tabs(["📊 Final Portfolio", "📝 Transformation Log", "📉 Risk Visualization", "💾 Export"])
        
        with tab1:
            st.subheader("Transformed Portfolio Positions")
            
            # Format the dataframe for display
            display_df = st.session_state['final_portfolio'].copy()
            display_df['Value per Unit'] = display_df['Value per Unit'].round(2)
            display_df['Total Value'] = display_df['Total Value'].round(2)
            display_df['Position'] = display_df['Position'].astype(int)
            
            # Color code by risk type
            def highlight_risk_type(row):
                if row['Risk Type'] == 'Long Stock':
                    return ['background-color: #e8f5e9'] * len(row)
                elif row['Risk Type'] == 'Call-like':
                    return ['background-color: #f3e5f5'] * len(row)
                elif row['Risk Type'] == 'Put Protection':
                    return ['background-color: #fff3e0'] * len(row)
                return [''] * len(row)
            
            styled_df = display_df.style.apply(highlight_risk_type, axis=1).format({
                'Strike': lambda x: f'{x:.0f}' if pd.notna(x) else '-',
                'Position': '{:,.0f}',
                'Value per Unit': '{:,.2f}',
                'Total Value': '{:,.2f}'
            })
            
            st.dataframe(styled_df, use_container_width=True, height=400)
            
            # Summary statistics
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                total_value = display_df['Total Value'].sum()
                st.metric("Total Portfolio Value", f"{total_value:,.0f}")
            
            with col2:
                long_exposure = display_df[display_df['Risk Type'] == 'Long Stock']['Total Value'].sum()
                st.metric("Long Stock Exposure", f"{long_exposure:,.0f}")
            
            with col3:
                call_exposure = display_df[display_df['Risk Type'] == 'Call-like']['Total Value'].sum()
                st.metric("Call-like Exposure", f"{call_exposure:,.0f}")
            
            with col4:
                put_protection = display_df[display_df['Risk Type'] == 'Put Protection']['Total Value'].sum()
                st.metric("Put Protection", f"{put_protection:,.0f}")
        
        with tab2:
            st.subheader("Step-by-Step Transformation Process")
            
            log_df = st.session_state['transformation_log']
            
            # Format the log for display
            log_display = log_df.copy()
            for col in ['Amount', 'Put Price', 'Synthetic Value']:
                if col in log_display.columns:
                    log_display[col] = log_display[col].apply(
                        lambda x: f'{float(x):,.2f}' if x != 'N/A' and pd.notna(x) else x
                    )
            
            st.dataframe(log_display, use_container_width=True, height=400)
            
            # Summary of transformation
            st.markdown(f"""
            <div class='success-box'>
            <b>Transformation Summary:</b><br>
            • Total steps executed: {len(log_df)}<br>
            • Synthetic calls created: {len(log_df[log_df['Action'] == 'Create Synthetic Call'])}<br>
            • Unmatched positions: {len(log_df[log_df['Action'] == 'Unmatched Puts'])}
            </div>
            """, unsafe_allow_html=True)
        
        with tab3:
            st.subheader("Portfolio Risk Visualization")
            
            fig_pie, fig_bar = create_risk_visualization(st.session_state['final_portfolio'])
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.plotly_chart(fig_pie, use_container_width=True)
            
            with col2:
                st.plotly_chart(fig_bar, use_container_width=True)
            
            # Strike distribution for options
            options_df = st.session_state['final_portfolio'][st.session_state['final_portfolio']['Strike'].notna()]
            
            if not options_df.empty:
                st.subheader("Strike Distribution")
                
                fig_strike = go.Figure()
                
                for option_type in options_df['Type'].unique():
                    type_df = options_df[options_df['Type'] == option_type]
                    fig_strike.add_trace(go.Bar(
                        x=type_df['Strike'],
                        y=type_df['Position'],
                        name=option_type,
                        text=type_df['Position'].apply(lambda x: f'{x:,.0f}'),
                        textposition='auto',
                    ))
                
                fig_strike.update_layout(
                    title='Position Distribution by Strike',
                    xaxis_title='Strike Price',
                    yaxis_title='Position Size',
                    barmode='group',
                    height=400
                )
                
                st.plotly_chart(fig_strike, use_container_width=True)
        
        with tab4:
            st.subheader("Export Transformed Portfolio")
            
            # Prepare export data
            export_df = st.session_state['final_portfolio'].copy()
            
            # Convert to CSV
            csv = export_df.to_csv(index=False)
            
            # Create download button
            st.download_button(
                label="📥 Download Transformed Portfolio (CSV)",
                data=csv,
                file_name=f"transformed_portfolio_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv"
            )
            
            # Also provide transformation log
            log_csv = st.session_state['transformation_log'].to_csv(index=False)
            
            st.download_button(
                label="📥 Download Transformation Log (CSV)",
                data=log_csv,
                file_name=f"transformation_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv"
            )
            
            st.markdown("""
            <div class='info-box'>
            <b>📌 Export includes:</b><br>
            • Final portfolio positions with risk classifications<br>
            • Synthetic call valuations<br>
            • Remaining unmatched positions<br>
            • Step-by-step transformation log
            </div>
            """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
