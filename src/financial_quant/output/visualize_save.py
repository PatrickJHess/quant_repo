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


def one_y_axis(x_data, y_data_list, title, series_labels, xlabel, ylabel,
                       markers, figure_size, y_limits,save_config={}, fill_config={},
                       colors=None):
    '''
    Plots data on a single y-axis.


    Args:
        x_data (array-like): Data for the x-axis.
        y_data_list (list of array-like): A list of datasets for the y-axis.
        title (str): The title of the graph.
        series_labels (list of str): Identifiers for each data series in the legend.
        xlabel (str): The label for the x-axis.
        ylabel (str): The label for the y-axis.
        markers (list of str): The markers to use for each series.
        figure_size (tuple): The width and height of the figure in inches.
        y_limits (tuple): The minimum and maximum values for the y-axis.
        save_config (dict, optional): Configuration for saving the file, passed
            to save_results(). Keys: 'volume', 'chapter', 'file_name'. Defaults to {}.
        fill_config (dict, optional): Configuration for filling areas.
            Keys: 'Between' (list of 1 or 2 indices from y_data_list),
                  'Start' (int, start index), 'End' (int, end index),
                  'Colors' (str), 'Labels' (str), 'Alpha' (float).
            Defaults to {}.
    Raises:
        ValueError: If input lists for series, markers, or colors do not match the number of y-datasets.
    '''
    import numpy as np
    from matplotlib import pyplot as plt
    num_series = len(y_data_list)
    # --- Input Validation ---
    if not all(len(lst) == num_series for lst in [series_labels, markers]):
        raise ValueError("The 'series_labels' and 'markers' lists must have the same length as 'y_data_list'.")


    if colors and len(colors) != num_series:
        raise ValueError("The 'colors' list must have the same length as 'y_data_list'.")


    # --- Plotting Setup ---
    fig = plt.figure(figsize=figure_size)
    fig.suptitle(title)
    plt.style.use('ggplot')


    if colors is None:
        # Generate a default color cycle if none are provided
        colors = plt.cm.viridis_r(np.linspace(0, 1, num_series))


# --- Plot Data Series ---
    for i in range(num_series):
        plt.plot(x_data, y_data_list[i], label=series_labels[i], marker=markers[i], color=colors[i])


    # --- Final Touches ---
    plt.ylim(y_limits)
    plt.xlabel(xlabel)
    plt.ylabel(ylabel)
    plt.legend()
    plt.tight_layout()


    # --- Save Figure ---
    # Calls the save_results function (assumed to be defined)


    path = save_results(save_config=save_config)
    if path:
     plt.savefig(path, dpi=300, bbox_inches='tight')


    plt.show()

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





