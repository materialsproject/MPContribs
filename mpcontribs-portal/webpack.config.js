const path = require("path");
const webpack = require('webpack');
const BundleTracker = require('webpack4-bundle-tracker');
const CompressionPlugin = require('compression-webpack-plugin');
const TerserJSPlugin = require('terser-webpack-plugin');
const MiniCssExtractPlugin = require('mini-css-extract-plugin');
const OptimizeCSSAssetsPlugin = require('optimize-css-assets-webpack-plugin');
const LodashModuleReplacementPlugin = require('lodash-webpack-plugin');
//const BundleAnalyzerPlugin = require('webpack-bundle-analyzer').BundleAnalyzerPlugin;
const devMode = process.env.NODE_ENV == 'development'
console.log('devMode = ' + devMode)

module.exports = {
    context: __dirname,
    entry: {
        'main': [
            path.resolve(__dirname, 'mpcontribs/portal/assets/js/analytics'),
            path.resolve(__dirname, 'mpcontribs/portal/assets/js/main'),
            //path.resolve(__dirname, 'mpcontribs/portal/assets/js/render_overview'),
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
        new MiniCssExtractPlugin({
            filename: "[name].[chunkhash].css",
            chunkFilename: '[name].[chunkhash].css'
        }),
        new LodashModuleReplacementPlugin({'paths': true})
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
            "underscore": 'underscore/underscore',
            "lunr": 'lunr.js/lunr',
            "clipboard": "clipboard-polyfill/dist/clipboard-polyfill",
            "plotly": 'plotly.js/lib/core',
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
            {
                test: /landingpage\.js$/, use: [{
                    // TODO babel for all: https://babeljs.io/docs/en/babel-plugin-syntax-dynamic-import/#installation
                    loader: 'babel-loader', options: {
                        'plugins': ['lodash'],
                        'presets': [['env', { 'modules': false, 'targets': { 'node': 4 } }]]
                    }
                }]
            },
            {
                test: /jquery-form/,
                use: [{
                    loader: 'imports-loader',
                    options: { imports: ['default jquery $'] }
                }]
            },
            {
                test: /jquery-validation/,
                use: [{
                    loader: 'imports-loader',
                    options: { imports: ['default jquery $'] }
                }]
            },
            {
                test: /jquery-simulate/,
                use: [{
                    loader: 'imports-loader',
                    options: { imports: ['default jquery $'] }
                }]
            },
            {
                test: /select2/,
                use: [{
                    loader: 'imports-loader',
                    options: { imports: ['default jquery $'] }
                }]
            },
            {
                test: /czmore/,
                use: [{
                    loader: 'imports-loader',
                    options: { imports: ['default jquery $'] }
                }]
            },
            {
                test: /linkify-element/,
                use: [{
                    loader: 'imports-loader',
                    options: { imports: ['side-effects linkify'] }
                }]
            }
        ]
    },
    mode : devMode ? 'development' : 'production'
}
