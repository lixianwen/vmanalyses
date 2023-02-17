import os
import glob
import logging
import datetime
from typing import Optional

from flask import (
    Flask,
    render_template,
    request,
    flash,
    redirect,
    url_for,
)
from werkzeug.utils import secure_filename
from jinja2 import Environment, FileSystemLoader
from pyecharts import options as opts
from pyecharts.charts import Bar, Pie
from pyecharts.globals import ThemeType, CurrentConfig
import pandas as pd

# 关于 CurrentConfig，可参考 [基本使用-全局变量]
CurrentConfig.GLOBAL_ENV = Environment(loader=FileSystemLoader("./templates"))

app = Flask(__name__, static_folder="templates")
UPLOAD_FOLDER = './'
ALLOWED_EXTENSIONS = {'csv'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['SECRET_KEY'] = 'whatever...'

vm = pd.read_csv('default.csv')

logger = logging.getLogger(__name__)


def unit_handler(size, unit):
    if unit == 'TB':
        return size * 1024
    return size


def init_vm():
    if vm.size:
        # pure memory
        vm['memory'] = vm['内存大小'].str.split(' ').str.get(0).astype(float)

        # 置备的空间
        vm['storage_size'] = vm['置备的空间'].str.replace(',', '').str.split(' ').str.get(0).astype(float)
        vm['storage_unit'] = vm['置备的空间'].str.replace(',', '').str.split(' ').str.get(1)
        vm['storage'] = list(map(lambda x, y: unit_handler(x, y), vm['storage_size'], vm['storage_unit']))

        # 从名称中分离出人和用途, 格式是：人名-用途-其他
        vm['username'] = vm['名称'].str.split('-').str.get(0)
        vm['usage'] = vm['名称'].str.split('-').str.get(1)


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def get_file_path_mtime(filepath: str) -> Optional[str]:
    format_timestamp = None
    if os.path.exists(filepath):
        timestamp = os.path.getmtime(filepath)
        format_timestamp = str(datetime.datetime.fromtimestamp(timestamp))

    return format_timestamp


@app.post('/upload')
def upload():
    if request.method == 'POST':
        # check if the post request has the file part
        if 'filename' not in request.files:
            flash('No file part')
            return redirect(url_for('index'))

        f = request.files['filename']
        # If the user does not select a file, the browser submits an
        # empty file without a filename.
        if f.filename == '':
            flash('No selected file')
            return redirect(url_for('index'))

        if f and allowed_file(f.filename):
            # Remove all the .csv file at first
            for csv_file in glob.iglob('*.csv'):
                try:
                    os.remove(csv_file)
                except os.error:
                    logger.warning(f'Failed to remove {csv_file!r}')
                    
            filename = secure_filename(f.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], 'default.csv')
            f.save(file_path)
            flash(f'文件 {filename} 最后修改时间: {get_file_path_mtime(file_path)}')

            global vm
            vm = pd.read_csv('default.csv')
            init_vm()

            return redirect(url_for('index'))


@app.get('/')
def index():
    init_vm()
    return render_template(
        'index.html',
        users=vm['username'].unique().tolist() if vm.size else [],
        users_online=vm[vm['状况'] == '已打开电源']['username'].unique().tolist() if vm.size else [],
        usages=vm['usage'].unique().tolist() if vm.size else [],
        usage_online=vm[vm['状况'] == '已打开电源']['usage'].unique().tolist() if vm.size else []
    )


@app.get('/summary/bar/<group>')
def summary_bar(group: str):
    if vm.size:
        online_vm = vm[vm['状况'] == '已打开电源']
        online_vm['memory'] = online_vm['memory'].astype(int)
        online_vm['storage'] = online_vm['storage'].astype(int)
        if group == 'username':
            user_usage_df = online_vm.groupby('username')[['memory', 'storage']].sum()
            user_usage_df = user_usage_df.sort_values(by=['memory'], ascending=False)
            c = (
                Bar(init_opts=opts.InitOpts(width='100%', height='400px'))
                .add_xaxis(user_usage_df.index.to_list())
                .add_yaxis('内存 GB', user_usage_df['memory'].to_list())
                .add_yaxis('置备空间 GB', user_usage_df['storage'].to_list())
                .set_global_opts(
                    title_opts=opts.TitleOpts(
                        pos_left='45%',
                        pos_top=20,
                    ),
                    datazoom_opts=opts.DataZoomOpts(range_start=0, range_end=100),
                    xaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(font_size=10))
                )
            )
        elif group == 'usage':
            usage_user_df = online_vm.groupby('usage')[['memory', 'storage']].sum()
            usage_user_df = usage_user_df.sort_values(by=['memory'], ascending=False)
            c = (
                Bar(init_opts=opts.InitOpts(width='100%', height='400px'))
                .add_xaxis(usage_user_df.index.to_list())
                .add_yaxis('内存 GB', usage_user_df['memory'].to_list())
                .add_yaxis('置备空间 GB', usage_user_df['storage'].to_list())
                .set_global_opts(
                    title_opts=opts.TitleOpts(
                        pos_left='45%',
                        pos_top=20,
                    ),
                    datazoom_opts=opts.DataZoomOpts(range_start=0, range_end=100),
                    xaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(font_size=10))
                )
            )
        else:
            return 'Only support group: username | usage'

        return c.render_embed()
    return 'Not data found!'


@app.get('/summary/pie/<group>/<series>')
def summary_pie(group: str, series: str):
    if vm.size:
        if group == 'username':
            if series == 'memory':
                user_usage_df = vm[vm['状况'] == '已打开电源'].groupby('username')[['memory', 'storage']].sum()

                c = (
                    Pie(init_opts=opts.InitOpts(height='700px'))
                    .add('内存 GB', list(zip(user_usage_df.index, user_usage_df['memory'])))
                    .set_global_opts(
                        title_opts={'text': '每个用户内存占用情况'},
                        legend_opts=opts.LegendOpts(is_show=False),
                    )
                    .set_series_opts(
                        label_opts=opts.LabelOpts(formatter='{b}: {c}')
                    )
                )
            elif series == 'storage':
                user_usage_df = vm.groupby('username')[['memory', 'storage']].sum()

                c = (
                    Pie(init_opts=opts.InitOpts(width='1000px', height='800px'))
                    .add('置备空间 GB', list(zip(user_usage_df.index, user_usage_df['storage'])))
                    .set_global_opts(
                        title_opts={'text': '每个用户置备空间占用情况'},
                        legend_opts=opts.LegendOpts(is_show=False),
                    )
                    .set_series_opts(
                        label_opts=opts.LabelOpts(formatter='{b}: {c}')
                    )
                )
            else:
                return 'Only support series: memory | storage'
        elif group == 'usage':
            if series == 'memory':
                usage_user_df = vm[vm['状况'] == '已打开电源'].groupby('usage')[['memory', 'storage']].sum()

                c = (
                    Pie(init_opts=opts.InitOpts(height='1000px'))
                    .add('内存 GB', list(zip(usage_user_df.index, usage_user_df['memory'])))
                    .set_global_opts(
                        title_opts={'text': '每个用途内存占用情况'},
                        legend_opts=opts.LegendOpts(is_show=False),
                    )
                    .set_series_opts(
                        label_opts=opts.LabelOpts(formatter='{b}: {c}')
                    )
                )
            elif series == 'storage':
                usage_user_df = vm.groupby('usage')[['memory', 'storage']].sum()

                c = (
                    Pie(init_opts=opts.InitOpts(width='1400px', height='1300px'))
                    .add('置备空间 GB', list(zip(usage_user_df.index, usage_user_df['storage'])))
                    .set_global_opts(
                        title_opts={'text': '每个用途置备空间占用情况'},
                        legend_opts=opts.LegendOpts(is_show=False),
                    )
                    .set_series_opts(
                        label_opts=opts.LabelOpts(formatter='{b}: {c}')
                    )
                )
            else:
                return 'Only support series: memory | storage'
        else:
            return 'Only support group: username | usage'

        return c.render_embed()

    return 'Not data found!'


@app.get('/user/bar')
def query_user():
    if vm.size:
        user = request.args['user']
        user_df = vm[(vm['username'] == user) & (vm['状况'] == '已打开电源')].groupby('usage')[['memory', 'storage']].sum()
        
        c = (
            Bar({'theme': ThemeType.MACARONS, 'width': '1500px'})
            .add_xaxis(user_df.index.to_list())
            .add_yaxis('内存 GB', user_df['memory'].to_list())
            .add_yaxis('置备空间 GB', user_df['storage'].to_list())
            .set_global_opts(
                title_opts={'text': f'根据用户: {user} 按用途聚合'},
                xaxis_opts=opts.AxisOpts(interval=0)
                # datazoom_opts=opts.DataZoomOpts(range_start=0, range_end=5)
            )
        )

        return c.render_embed()
    return 'Not data found!'


@app.get('/user/pie/<series>')
def user_pie(series: str):
    if vm.size:
        user = request.args['user']
        
        if series == 'memory':
            user_df = vm[(vm['username'] == user) & (vm['状况'] == '已打开电源')].groupby('usage')[['memory', 'storage']].sum()
            c = (
                Pie()
                .add('内存 GB', list(zip(user_df.index, user_df['memory'])))
                .set_global_opts(
                    title_opts={'text': f'用户: {user} 的每个用途内存占用情况'}
                )
                .set_series_opts(
                    label_opts=opts.LabelOpts(formatter='{b}: {c}')
                )
            )
        elif series == 'storage':
            user_df = vm[vm['username'] == user].groupby('usage')[['memory', 'storage']].sum()

            c = (
                Pie()
                .add('置备空间 GB', list(zip(user_df.index, user_df['storage'])))
                .set_global_opts(
                    title_opts={'text': f'用户: {user} 的每个用途置备空间占用情况'}
                )
                .set_series_opts(
                    label_opts=opts.LabelOpts(formatter='{b}: {c}')
                )
            )
        else:
            return 'Only support series: memory | storage'

        return c.render_embed()
    return 'Not data found!'


@app.get('/usage/bar')
def query_usage():
    if vm.size:
        usage = request.args['usage']
        usage_df = vm[(vm['usage'] == usage) & (vm['状况'] == '已打开电源')].groupby('username')[['memory', 'storage']].sum()
        
        c = (
            Bar({'theme': ThemeType.MACARONS, 'width': '1500px'})
            .add_xaxis(usage_df.index.to_list())
            .add_yaxis('内存 GB', usage_df['memory'].to_list())
            .add_yaxis('置备空间 GB', usage_df['storage'].to_list())
            .set_global_opts(
                title_opts={'text': f'根据用途: {usage} 按用户聚合'},
                xaxis_opts=opts.AxisOpts(interval=0)
                # datazoom_opts=opts.DataZoomOpts(range_start=0, range_end=5)
            )
        )

        return c.render_embed()
    return 'Not data found!'


@app.get('/usage/pie/<series>')
def usage_pie(series: str):
    if vm.size:
        usage = request.args['usage']

        if series == 'memory':
            usage_df = vm[(vm['usage'] == usage) & (vm['状况'] == '已打开电源')].groupby('username')[['memory', 'storage']].sum()
            c = (
                Pie()
                .add('内存 GB', list(zip(usage_df.index, usage_df['memory'])))
                .set_global_opts(
                    title_opts={'text': f'用途: {usage} 的每个用户内存占用情况'}
                )
                .set_series_opts(
                    label_opts=opts.LabelOpts(formatter='{b}: {c}')
                )
            )
        elif series == 'storage':
            usage_df = vm[vm['usage'] == usage].groupby('username')[['memory', 'storage']].sum()

            c = (
                Pie()
                .add('置备空间 GB', list(zip(usage_df.index, usage_df['storage'])))
                .set_global_opts(
                    title_opts={'text': f'用途: {usage} 的每个用户置备空间占用情况'}
                )
                .set_series_opts(
                    label_opts=opts.LabelOpts(formatter='{b}: {c}')
                )
            )
        else:
            return 'Only support series: memory | storage'

        return c.render_embed()
    return 'Not data found!'


if __name__ == "__main__":
    app.run(host='0.0.0.0', debug=True)
