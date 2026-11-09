import os
import sys
import re
import pandas as pd
import numpy as np
from pathvalidate import sanitize_filepath
from matplotlib import pyplot as plt
import openpyxl
from openpyxl.utils import get_column_letter
from IPython.display import display, Markdown as md
from pathlib import Path
import altair as alt

def one_y_axis(x_data, y_data_list, title="", xlabel="", ylabel="",
                     series_labels=None, markers=None, colors=None,
                     figure_size=(10, 6), y_limits=None,
                     save_config=None, fill_config=None, ax=None): # <-- Added ax parameter
    """
    Plots data on a single y-axis. Can plot standalone or onto an existing subplot.

    Args:
        x_data (array-like): Data for the x-axis.
        y_data_list (list of array-like): A list of datasets for the y-axis.
        title (str, optional): The title of the graph.
        xlabel (str, optional): The label for the x-axis.
        ylabel (str, optional): The label for the y-axis.
        series_labels (list of str, optional): Identifiers for each data series. 
        markers (list of str, optional): The markers to use for each series.
        colors (list of str, optional): Colors for each series.
        figure_size (tuple, optional): The width and height of the figure in inches. Defaults to (10, 6).
        y_limits (tuple, optional): The (min, max) values for the y-axis.
        save_config (dict, optional): Config for saving the file. Keys: 'volume', 'chapter', 'file_name'.
        fill_config (dict, optional): Config for filling areas. Keys: 'Between' (list of 1 or 2 indices),
                                      'Start', 'End', 'Colors', 'Labels', 'Alpha'.
        ax (matplotlib.axes.Axes, optional): An existing axes object to plot on. If None, creates a new figure.

      Returns:
        matplotlib.axes.Axes: The axes object containing the plot.
    """
    num_series = len(y_data_list)

    # --- Smart Defaults (Frictionless Inputs) ---
    series_labels = series_labels or [f"Series {i+1}" for i in range(num_series)]
    markers = markers or [""] * num_series
    colors = colors or plt.cm.viridis_r(np.linspace(0, 1, num_series))

    # Input Validation
    if not (len(series_labels) == len(markers) == len(colors) == num_series):
        raise ValueError("Lengths of 'series_labels', 'markers', and 'colors' must match 'y_data_list'.")

    # --- Plotting Setup (Protects Global State) ---
    with plt.style.context('ggplot'):

        # Determine if we are building a new figure or using an existing subplot
        if ax is None:
            fig, current_ax = plt.subplots(figsize=figure_size)
            is_standalone = True
        else:
            current_ax = ax
            is_standalone = False

        # Use set_title so it applies correctly to subplots, not just the master figure
        if title:
            current_ax.set_title(title)

        # --- Pythonic Loop ---
        for y_data, label, marker, color in zip(y_data_list, series_labels, markers, colors):
            current_ax.plot(x_data, y_data, label=label, marker=marker, color=color)

        # --- Implement the Fill Feature ---
        if fill_config:
            indices = fill_config.get('Between', [0])
            y1 = y_data_list[indices[0]]
            y2 = y_data_list[indices[1]] if len(indices) > 1 else np.zeros_like(y1)

            start, end = fill_config.get('Start', 0), fill_config.get('End', len(x_data))

            current_ax.fill_between(
                x_data[start:end], y1[start:end], y2[start:end],
                color=fill_config.get('Colors', 'gray'),
                alpha=fill_config.get('Alpha', 0.3),
                label=fill_config.get('Labels', None)
            )

        # --- Final Touches ---
        if y_limits:
            current_ax.set_ylim(y_limits)
        current_ax.set_xlabel(xlabel)
        current_ax.set_ylabel(ylabel)
        current_ax.legend(loc='upper right')

        # --- Save & Show (Only if standalone) ---
        # We prevent plt.show() if passing an ax, so the parent script can build the full dashboard first
        if is_standalone:
            plt.tight_layout()
            if save_config:
                path = save_results(save_config=save_config)
                if path:
                    plt.savefig(path, dpi=300, bbox_inches='tight')
            plt.show()

        return current_ax

def stacked_charts(top_x_data, top_data_list,bottom_data_list, 
                   bottom_x_data=None, share_x_axis=True, 
                   top_config=None, bottom_config=None, 
                   top_secondary_data_list=None, top_secondary_config=None,
                   bottom_secondary_data_list=None, bottom_secondary_config=None,
                   figure_size=(10, 8), height_ratios=[2, 1], hspace=0.1,
                   save_config=None):
    """
    Creates a stacked two-panel chart.

    Args:
        top_x_data (array-like): X-axis data for the top chart.
        top_data_list (list of array-like): Datasets for the top chart.
        bottom_data_list (list of array-like): Datasets for the bottom chart.
        bottom_x_data (array-like, optional): X-axis data for the bottom chart. 
            If None, falls back to using `top_x_data`. Defaults to None.
        share_x_axis (bool, optional): If True, links the top and bottom x-axes 
            and hides the top x-axis labels. Defaults to True.
        ... [other args remain the same] ...
    """
    # If no separate bottom x-data is provided, assume they share the same x-axis
    if bottom_x_data is None:
        bottom_x_data = top_x_data

    top_config = top_config or {}
    bottom_config = bottom_config or {}
    top_secondary_config = top_secondary_config or {}
    bottom_secondary_config = bottom_secondary_config or {}

    with plt.style.context('ggplot'):
        fig, (ax1, ax2) = plt.subplots(
            2, 1, 
            figsize=figure_size, 
            sharex=share_x_axis, # <-- Now configurable
            gridspec_kw={'height_ratios': height_ratios}
        )
        fig.subplots_adjust(hspace=hspace)

        # --- 1. Top Chart ---
        one_y_axis(top_x_data, top_data_list, ax=ax1, **top_config)
        
        if top_secondary_data_list:
            ax1_twin = ax1.twinx()
            ax1_twin.grid(False) 
            one_y_axis(top_x_data, top_secondary_data_list, ax=ax1_twin, **top_secondary_config)

        # --- 2. Bottom Chart ---
        one_y_axis(bottom_x_data, bottom_data_list, ax=ax2, **bottom_config)
        
        if bottom_secondary_data_list:
            ax2_twin = ax2.twinx()
            ax2_twin.grid(False)
            one_y_axis(bottom_x_data, bottom_secondary_data_list, ax=ax2_twin, **bottom_secondary_config)

        plt.tight_layout()
        
        if save_config:
            path = save_results(save_config=save_config)
            if path:
                plt.savefig(path, dpi=300, bbox_inches='tight')
        
        plt.show()
        
        return fig, (ax1, ax2)

def create_workbook(df,sheet_name='sheet1', save_config=None):
    """
    Writes a DataFrame to a specific sheet in an Excel workbook and auto-fits
    column widths for readability.


    Args:
        sheet_name (str): The name of the sheet to create or replace.
        df (pd.DataFrame): The DataFrame to write.
        save_config (dict, optional): Configuration for saving the file, passed
         Keys: 'volume':folder, 'chapter':'subfolder, 'file_name':file name. Defaults to {}.     
    """



    
    # Fix mutable default argument
    if save_config is None:
        save_config = {}


    # --- 1. Sanitize Sheet Name ---
    sane_sheet_name = re.sub(r'[\\*?:/\[\]]', '', str(sheet_name))
    if len(sane_sheet_name) > 31:
        sane_sheet_name = sane_sheet_name[:31]
    if not sane_sheet_name:
        sane_sheet_name = "Sheet1"


    # --- 2. Get Save Path ---
    file_name = save_config.get('file_name', 'output.xlsx')
    if not file_name.endswith('.xlsx'):
        file_name += '.xlsx'
    save_config['file_name']=file_name
    # Assuming save_results is defined elsewhere in your code
    try:
        path_filename = save_results(save_config=save_config)
        if path_filename is None:
            path_filename = file_name
    except NameError:
        # Fallback if save_results is not defined
        path_filename = file_name


    # --- 3. Write and Format ---
    try:
        # Create empty workbook if it doesn't exist to allow 'append' mode
        if not os.path.exists(path_filename):
            pd.DataFrame().to_excel(path_filename, sheet_name="Sheet1")


        # Write DataFrame
        with pd.ExcelWriter(
            path_filename,
            mode='a',
            engine='openpyxl',
            if_sheet_exists='replace',
            datetime_format='YYYY-MM-DD'
        ) as writer:
            # FIXED: Using sane_sheet_name instead of sheet_name
            df.to_excel(writer, sheet_name=sane_sheet_name, index=True)


        # Format with openpyxl
        workbook = openpyxl.load_workbook(path_filename)
        
        # FIXED: Using sane_sheet_name
        try:
            ws = workbook[sane_sheet_name]
        except KeyError:
            print(f"Error: Sheet '{sane_sheet_name}' not found after writing.")
            return


        # Auto-fit columns
        for col_idx, column_cells in enumerate(ws.columns, 1):
            max_length = 0
            column_letter = get_column_letter(col_idx)


            for cell in column_cells:
                try:
                    if cell.value: # Check if cell is not empty
                        cell_length = len(str(cell.value))
                        if cell_length > max_length:
                            max_length = cell_length
                except Exception:
                    pass


            ws.column_dimensions[column_letter].width = max_length + 2


        # Delete default Sheet1 if necessary
        if 'Sheet1' in workbook.sheetnames and sane_sheet_name != 'Sheet1' and len(workbook.sheetnames) > 1:
            del workbook['Sheet1']
            
        workbook.save(path_filename)
        display(md(f"### ***✅ Successfully wrote and formatted sheet {sane_sheet_name} in {path_filename}***"))
        
    except Exception as e:
        display(md("### ❌ **ERROR during Excel write/format:**"))
        print(f"Exception details: {e}")

def save_results(save_config: dict = None):
    """
    Interactively prompts the user to confirm and generate a safe save path.


    This function pauses execution and asks the user (y/n) if they want to save
    a file. It is environment-aware:


    - **In Google Colab:** It attempts to use '/content/drive/MyDrive'. If not
      mounted, it will try to mount it. If mounting fails, it falls back
      to the temporary '/content' directory and issues a warning.
    - **In a local environment:** It uses the current working directory.


    The function constructs a full path from the base folder and the optional
    'volume' and 'chapter' subdirectories. All path components are sanitized
    using `pathvalidate`.


    Args:
        save_config (dict, optional): A dictionary containing path components.
            'volume' (str, optional): The name of a top-level subdirectory.
            'chapter' (str, optional): The name of a nested subdirectory.
            'file_name' (str, optional): The final file name.
                Defaults to 'output.txt' if not provided or if sanitization
                results in an empty string.


    Returns:
        str or None: A complete, sanitized, absolute string path to the
            file if the user confirms 'y' and path creation succeeds.
            Returns None if the user chooses 'n' or if an error occurs.
    
    Example:
        config = {
            'volume': 'My_Notebooks',
            'chapter': 'Chapter_01',
            'file_name': 'results.json'
        }
        save_path = save_results(config)
        
        # User inputs 'y'
        
        if save_path:
            # save_path might be '/content/drive/MyDrive/My_Notebooks/Chapter_01/results.json'
            print(f"Saving to: {save_path}")
            # ... proceed to write file ...
    """



    save_config = save_config or {}


    # --- Handle IPython imports safely ---
    is_colab = 'google.colab' in sys.modules
    try:
        from IPython.display import display, Markdown as md
        def display_msg(text): display(md(text))
    except ImportError:
        def display_msg(text): print(text.replace('###', '').replace('*', ''))


    # --- 1. Get user's choice (y/n) ---
    default_value = "n"
    prompt = "❓ Do you want to save the file? (y/n) (press enter for n): "


    try:
        raw_input = input(prompt).strip().lower()
        choice = raw_input if raw_input else default_value
    except (EOFError, KeyboardInterrupt):
        return None


    while choice not in ['y', 'n']:
        choice = input(prompt).strip().lower()


    # --- 2. Handle "No" ---
    if choice == 'n':
        display_msg('### ***❌ File Not Saved***.')
        return None


    # --- 3. Handle "Yes" ---
    display_msg("### ***⌛ Generating A Path***")


    # --- Get and sanitize config values ---
    volume = sanitize_filepath(save_config.get('volume', ''))
    chapter = sanitize_filepath(save_config.get('chapter', ''))
    
    # The caller should provide the extension, but we fall back to a generic name just in case
    file_name = sanitize_filepath(save_config.get('file_name', 'output'))
    if not file_name:
        file_name = 'output'


    subfolder = os.path.join(volume, chapter)


    # --- Drive/Folder Logic ---
    base_folder = ''
    drive_path = '/content/drive/MyDrive'
    
    if is_colab:
        if os.path.exists(drive_path):
            base_folder = drive_path
        else:
            try:
                from google.colab import drive
                drive.mount('/content/drive')
                base_folder = drive_path
            except Exception as e:
                base_folder = '/content'
                display_msg(f"### ⚠️ **Drive Mount Failed:** {e}. Saving to temporary '/content' folder.")
    else:
        base_folder = os.getcwd()


    # --- Path Creation ---
    try:
        full_folder_path = os.path.join(base_folder, subfolder)
        path_obj = Path(full_folder_path)
        path_obj.mkdir(parents=True, exist_ok=True)
        
        final_path_str = os.path.join(str(path_obj), file_name)


        display_msg(f'### ✅ **File Path Generated:**\n`{final_path_str}`')
        
        if base_folder == '/content':
            display_msg('### ⚠️ *File is in a temporary location and will be lost on runtime restart.*')


        return final_path_str


    except Exception as e:
        display_msg('### ❌ **ERROR Creating Directory:**')
        print(e)
        return None


def graph_uncertainty_arb(df_list, asset):
    """
    Generates a 2-tier dashboard:
    Top Row: Static side-by-side Volume and Closing Price charts.
    Bottom Row: Interactive Overview/Detail chart explicitly for Closing Price.
    """
    # 1. Prepare the combined dataset
    df_combined = pd.concat(df_list).reset_index(names='date')

    price_domain = [df_combined['close'].min() * 0.9, df_combined['close'].max() * 1.1]
    volume_domain = [df_combined['volume'].min() * 0.9, df_combined['volume'].max() * 1.1]

    # Shared base chart ensures both rows get the legend by default
    base_chart = alt.Chart(df_combined).mark_line().encode(
        color=alt.Color('symbol:N', legend=alt.Legend(title="Symbol"))
    )

    # --- TOP ROW: Static Side-by-Side ---
    volume_chart = base_chart.encode(
        x=alt.X('date:T', title='Date'),
        y=alt.Y('volume:Q', title='Volume', scale=alt.Scale(domain=volume_domain))
    ).properties(
        width=300, height=350, title=f'{asset} Trading Volume - Full Timeline'
    )

    price_chart = base_chart.encode(
        x=alt.X('date:T', title='Date'),
        y=alt.Y('close:Q', title='Price', scale=alt.Scale(domain=price_domain))
    ).properties(
        width=300, height=350, title=f'{asset} Closing Prices - Arb Effect'
    )

    top_row = volume_chart | price_chart


    # --- BOTTOM ROW: Interactive Arb Effect (Price Only) ---
    brush = alt.selection_interval(encodings=['x'])

    price_base = base_chart.encode(
        y=alt.Y('close:Q', title='Price', scale=alt.Scale(domain=price_domain))
    )

    # Upper Detailed Price Chart (Keeps the legend from base_chart)
    price_upper = price_base.encode(
        x=alt.X('date:T', scale=alt.Scale(domain=brush), title='')
    ).properties(
        width=650, height=260, title=f'Interactive Detail: {asset} Arb Effect'
    )

    # Lower Overview Price Chart (Legend explicitly hidden)
    price_lower = price_base.encode(
        x=alt.X('date:T', title='Date (Drag to Zoom)'),
        color=alt.Color('symbol:N', legend=None) 
    ).properties(
        width=650, height=150
    ).add_params(
        brush
    )

    bottom_row = price_upper & price_lower


    # --- FINAL DASHBOARD COMBINATION ---
    # We resolve the legend independently so Altair doesn't try to force 
    # the top row and bottom row to share a single, awkwardly placed legend.
    final_dashboard = (top_row & bottom_row).resolve_legend(
        color="independent"
    )

    return final_dashboard

