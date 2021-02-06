const path = require("path");
const webpack = require('webpack');
const BundleTracker = require('webpack4-bundle-tracker');
const CompressionPlugin = require('compression-webpack-plugin');
const TerserJSPlugin = require('terser-webpack-plugin');
const MiniCssExtractPlugin = require('mini-css-extract-plugin');
const LodashModuleReplacementPlugin = require('lodash-webpack-plugin');
const devMode = process.env.NODE_ENV == 'development'
console.log('devMode = ' + devMode)

module.exports = {
    context: __dirname,
    entry: {
        'main': path.resolve(__dirname, 'mpcontribs/portal/assets/js/main'),
        'browse': path.resolve(__dirname, 'mpcontribs/portal/assets/js/browse'),
        'search': path.resolve(__dirname, 'mpcontribs/portal/assets/js/search'),
        'apply': path.resolve(__dirname, 'mpcontribs/portal/assets/js/apply'),
        'work': path.resolve(__dirname, 'mpcontribs/portal/assets/js/work'),
        'landingpage': path.resolve(__dirname, 'mpcontribs/portal/assets/js/landingpage'),
        'contribution': path.resolve(__dirname, 'mpcontribs/portal/assets/js/contribution'),
        //path.resolve(__dirname, 'mpcontribs/portal/assets/js/render_overview'),
    },
    output: {
        filename: "[name].[chunkhash].js",
        chunkFilename: '[name].[chunkhash].js',
        crossOriginLoading: "anonymous",
        publicPath: '/static/',
        assetModuleFilename: 'assets/[name][ext]'
    },
    plugins: [
        new BundleTracker({filename: './webpack-stats.json'}),
        new webpack.ProvidePlugin({
            _: "underscore", $: "jquery", jquery: "jquery",
            "window.jQuery": "jquery", jQuery: "jquery"
        }),
        new CompressionPlugin({minRatio: 1}),
        new MiniCssExtractPlugin({
            filename: "[name].[chunkhash].css",
            chunkFilename: '[name].[chunkhash].css'
        }),
        new LodashModuleReplacementPlugin({'paths': true})
    ],
    optimization: {
        minimizer: [new TerserJSPlugin({})],
        minimize: true,
        moduleIds: "deterministic"
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
            "plotly": 'plotly.js/lib/core',
            "js-cookie": 'js-cookie/src/js.cookie',
            //mathjs": 'mathjs/dist/math',
        }
    },
    module: {
        rules: [
            {
                test: /\.(gif|png|jpe?g)$/i, type: 'asset'
            }, {
                test: /\.(woff(2)?|ttf|eot|svg)(\?v=[0-9]\.[0-9]\.[0-9])?$/, type: 'asset'
            }, {
                test: /\.scss$/,
                use: [
                    MiniCssExtractPlugin.loader, {loader: 'css-loader'},
                    {loader: 'sass-loader', options: {sourceMap: true}}
                ]
            }, {
                test: /\.css$/,
                use: [MiniCssExtractPlugin.loader, {loader: "css-loader"}]
            }, {
                test: /landingpage\.js$/, use: [{
                    // TODO babel for all: https://babeljs.io/docs/en/babel-plugin-syntax-dynamic-import/#installation
                    loader: 'babel-loader', options: {
                        'plugins': ['lodash'], 'presets': ['@babel/preset-env']
                    }
                }]
            }, {
                test: /\.mjs$/,
                include: /node_modules/,
                type: "javascript/auto"
            }, {
                test: /jquery-form/,
                use: [{
                    loader: 'imports-loader',
                    options: { imports: ['default jquery $'] }
                }]
            }, {
                test: /jquery-validation/,
                use: [{
                    loader: 'imports-loader',
                    options: { imports: ['default jquery $'] }
                }]
            }, {
                test: /jquery-simulate/,
                use: [{
                    loader: 'imports-loader',
                    options: { imports: ['default jquery $'] }
                }]
            }, {
                test: /select2/,
                use: [{
                    loader: 'imports-loader',
                    options: { imports: ['default jquery $'] }
                }]
            }, {
                test: /czmore/,
                use: [{
                    loader: 'imports-loader',
                    options: { imports: ['default jquery $'] }
                }]
            }
        ]
    },
    mode : devMode ? 'development' : 'production'
}
