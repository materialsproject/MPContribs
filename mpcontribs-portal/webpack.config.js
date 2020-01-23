const path = require("path");
const webpack = require('webpack');
const BundleTracker = require('webpack4-bundle-tracker');
const CompressionPlugin = require('compression-webpack-plugin');
const TerserJSPlugin = require('terser-webpack-plugin');
const MiniCssExtractPlugin = require('mini-css-extract-plugin');
const OptimizeCSSAssetsPlugin = require('optimize-css-assets-webpack-plugin');
//const BundleAnalyzerPlugin = require('webpack-bundle-analyzer').BundleAnalyzerPlugin;
const devMode = process.env.NODE_ENV == 'development'
console.log('devMode = ' + devMode)

module.exports = {
    context: __dirname,
    entry: {
        'main': [
            path.resolve(__dirname, 'mpcontribs/portal/assets/js/analytics'),
            path.resolve(__dirname, 'mpcontribs/portal/assets/js/main'),
            path.resolve(__dirname, 'mpcontribs/portal/assets/js/render_json'),
            path.resolve(__dirname, 'mpcontribs/portal/assets/js/render_table'),
            path.resolve(__dirname, 'mpcontribs/portal/assets/js/render_plot'),
            path.resolve(__dirname, 'mpcontribs/portal/assets/js/render_overview'),
        ]
    },
    output: {
        path: path.resolve(__dirname, 'dist'),
        filename: "[name].[chunkhash].js",
        chunkFilename: '[name].[chunkhash].js',
        crossOriginLoading: "anonymous",
        publicPath: '/static/'
    },
    plugins: [
        //new BundleAnalyzerPlugin(),
        new BundleTracker({filename: './webpack-stats.json'}),
        new webpack.ProvidePlugin({
            _: "underscore", $: "jquery", jquery: "jquery",
            "window.jQuery": "jquery", jQuery: "jquery"
        }),
        new webpack.HashedModuleIdsPlugin(),
        new CompressionPlugin({minRatio: 1}),
        new webpack.EnvironmentPlugin(['NODE_ENV', 'API_CNAME']),
        new MiniCssExtractPlugin({
            filename: "[name].[chunkhash].css",
            chunkFilename: '[name].[chunkhash].css'
        })
    ],
    optimization: {
        minimizer: [new TerserJSPlugin({}), new OptimizeCSSAssetsPlugin({})],
        minimize: true
    },
    resolve: {
        modules: [
            path.resolve(__dirname, 'mpcontribs/portal/assets'),
            path.resolve(__dirname, 'mpcontribs/users'),
            path.resolve(__dirname, 'node_modules')
        ],
        extensions: ['.js'],
        alias: {
            "jquery": 'jquery/src/jquery',
            "jquery-validation": 'jquery-validation/dist/jquery.validate',
            "jquery-form": 'jquery-form/src/jquery.form',
            "czmore": 'js/jquery.czMore-latest',
            "typy": 'typy/lib/index',
            "backbone": 'backbone/backbone',
            "underscore": 'underscore/underscore',
            "lunr": 'lunr.js/lunr',
            "clipboard": "clipboard-polyfill/dist/clipboard-polyfill",
            "plotly": 'plotly.js/lib/core',
            "backgrid-select-all": 'backgrid-select-all/backgrid-select-all',
            "backbone.paginator": 'backbone.paginator/lib/backbone.paginator',
            "js-cookie": 'js-cookie/src/js.cookie',
            "linkify": 'linkifyjs/lib/linkify',
            "linkify-element": 'linkifyjs/lib/linkify-element',
            "mathjs": 'mathjs/dist/math',
        }
    },
    module: {
        rules: [
            {
                test: /\.(gif|png|jpe?g)$/i,
                use: [
                    {loader: 'url-loader', options: {limit: 8192, name:'[name].[ext]', outputPath: 'assets'}},
                    {loader: 'image-webpack-loader'}
                ],
            },
            {
                test: /\.(woff(2)?|ttf|eot|svg)(\?v=[0-9]\.[0-9]\.[0-9])?$/, loader: 'url-loader',
                options: { limit: 8192, name:'[name].[ext]', outputPath: 'assets' }
            },
            {
                test: /\.scss$/,
                use: [
                    MiniCssExtractPlugin.loader, {loader: 'css-loader'},
                    {loader: 'sass-loader', options: {sourceMap: true}}
                ]
            },
            { test: /\.css$/, loaders: [MiniCssExtractPlugin.loader, "css-loader"] },
            { test: /backbone/, loader: 'exports-loader?Backbone!imports-loader?underscore,jquery' },
            { test: /backgrid/, loader: 'imports-loader?jquery,backbone' },
            { test: /jquery-form/, loader: 'imports-loader?jquery' },
            { test: /jquery-validation/, loader: 'imports-loader?jquery' },
            { test: /select2/, loader: 'imports-loader?jquery' },
            { test: /czmore/, loader: 'imports-loader?jquery' },
            { test: /backgrid-select-all/, loader: 'imports-loader?backgrid' },
            { test: /backgrid-filter/, loader: 'imports-loader?backgrid' },
            { test: /backbone.paginator/, loader: 'imports-loader?backbone' },
            { test: /backgrid-paginator/, loader: 'imports-loader?backgrid,backbone.paginator' },
            { test: /backgrid-grouped-columns/, loader: 'imports-loader?backgrid' },
            { test: /backgrid-columnmanager/, loader: 'imports-loader?backgrid' },
            { test: /linkify-element/, loader: 'imports-loader?linkify' }
        ]
    },
    mode : devMode ? 'development' : 'production'
}
