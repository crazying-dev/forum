const Live2DLPK = (function () {
    let _lpkUrl = '';
    let _container = null;
    let _canvas = null;
    let _app = null;
    let _model = null;
    let _modelBaseW = 0;
    let _modelBaseH = 0;
    let _onProgress = null;
    let _resizeTimer = null;
    let _resizeObserver = null;
    let _resizeListener = null;

    function md5Hash(str) {
        const rotateLeft = (value, shift) => (value << shift) | (value >>> (32 - shift));
        
        const addUnsigned = (x, y) => {
            const lsw = (x & 0xFFFF) + (y & 0xFFFF);
            const msw = (x >> 16) + (y >> 16) + (lsw >> 16);
            return (msw << 16) | (lsw & 0xFFFF);
        };
        
        const md5Round = (a, b, c, d, x, s, ac) => {
            const f = (b & c) | (~b & d);
            return addUnsigned(rotateLeft(addUnsigned(addUnsigned(a, f), addUnsigned(x, ac)), s), b);
        };
        
        const md5Round2 = (a, b, c, d, x, s, ac) => {
            const f = (b & d) | (c & ~d);
            return addUnsigned(rotateLeft(addUnsigned(addUnsigned(a, f), addUnsigned(x, ac)), s), b);
        };
        
        const md5Round3 = (a, b, c, d, x, s, ac) => {
            const f = b ^ c ^ d;
            return addUnsigned(rotateLeft(addUnsigned(addUnsigned(a, f), addUnsigned(x, ac)), s), b);
        };
        
        const md5Round4 = (a, b, c, d, x, s, ac) => {
            const f = c ^ (b | ~d);
            return addUnsigned(rotateLeft(addUnsigned(addUnsigned(a, f), addUnsigned(x, ac)), s), b);
        };
        
        const state = [0x67452301, 0xEFCDAB89, 0x98BADCFE, 0x10325476];
        const constants = [
            0xD76AA478, 0xE8C7B756, 0x242070DB, 0xC1BDCEEE,
            0xF57C0FAF, 0x4787C62A, 0xA8304613, 0xFD469501,
            0x698098D8, 0x8B44F7AF, 0xFFFF5BB1, 0x895CD7BE,
            0x6B901122, 0xFD987193, 0xA679438E, 0x49B40821,
            0xF61E2562, 0xC040B340, 0x265E5A51, 0xE9B6C7AA,
            0xD62F105D, 0x02441453, 0xD8A1E681, 0xE7D3FBC8,
            0x21E1CDE6, 0xC33707D6, 0xF4D50D87, 0x455A14ED,
            0xA9E3E905, 0xFCEFA3F8, 0x676F02D9, 0x8D2A4C8A,
            0xFFFA3942, 0x8771F681, 0x6D9D6122, 0xFDE5380C,
            0xA4BEEA44, 0x4BDECFA9, 0xF6BB4B60, 0xBEBFBC70,
            0x289B7EC6, 0xEAA127FA, 0xD4EF3085, 0x04881D05,
            0xD9D4D039, 0xE6DB99E5, 0x1FA27CF8, 0xC4AC5665,
            0xF4292244, 0x432AFF97, 0xAB9423A7, 0xFC93A039,
            0x655B59C3, 0x8F0CCC92, 0xFFEFF47D, 0x85845DD1,
            0x6FA87E4F, 0xFE2CE6E0, 0xA3014314, 0x4E0811A1,
            0xF7537E82, 0xBD3AF235, 0x2AD7D2BB, 0xEB86D391
        ];
        
        const shifts = [
            7, 12, 17, 22, 7, 12, 17, 22, 7, 12, 17, 22, 7, 12, 17, 22,
            5, 9, 14, 20, 5, 9, 14, 20, 5, 9, 14, 20, 5, 9, 14, 20,
            4, 11, 16, 23, 4, 11, 16, 23, 4, 11, 16, 23, 4, 11, 16, 23,
            6, 10, 15, 21, 6, 10, 15, 21, 6, 10, 15, 21, 6, 10, 15, 21
        ];
        
        const input = [];
        const inputLen = str.length * 8;
        
        for (let i = 0; i < str.length; i++) {
            input[i >> 2] |= str.charCodeAt(i) << ((i % 4) * 8);
        }
        
        input[str.length >> 2] |= 0x80 << ((str.length % 4) * 8);
        input[(((str.length + 8) >>> 6) << 4) + 14] = inputLen;
        
        for (let i = 0; i < input.length; i += 16) {
            const [aa, bb, cc, dd] = state;
            
            let a = aa, b = bb, c = cc, d = dd;
            
            for (let j = 0; j < 16; j++) {
                a = md5Round(a, b, c, d, input[i + j], shifts[j], constants[j]);
                [a, b, c, d] = [d, a, b, c];
            }
            
            for (let j = 16; j < 32; j++) {
                a = md5Round2(a, b, c, d, input[i + ((j * 5 + 1) % 16)], shifts[j], constants[j]);
                [a, b, c, d] = [d, a, b, c];
            }
            
            for (let j = 32; j < 48; j++) {
                a = md5Round3(a, b, c, d, input[i + ((j * 3 + 5) % 16)], shifts[j], constants[j]);
                [a, b, c, d] = [d, a, b, c];
            }
            
            for (let j = 48; j < 64; j++) {
                a = md5Round4(a, b, c, d, input[i + (j * 7 % 16)], shifts[j], constants[j]);
                [a, b, c, d] = [d, a, b, c];
            }
            
            state[0] = addUnsigned(state[0], a);
            state[1] = addUnsigned(state[1], b);
            state[2] = addUnsigned(state[2], c);
            state[3] = addUnsigned(state[3], d);
        }
        
        let result = '';
        for (let i = 0; i < 4; i++) {
            const val = state[i];
            for (let j = 0; j < 4; j++) {
                const byte = (val >> (j * 8)) & 0xFF;
                result += byte.toString(16).padStart(2, '0');
            }
        }
        
        return Promise.resolve(result);
    }

    function lpkGenKey(str) {
        let ret = 0;
        for (let i = 0; i < str.length; i++) {
            ret = (ret * 31 + str.charCodeAt(i)) & 0xffffffff;
        }
        if (ret & 0x80000000) {
            ret = ret | 0xffffffff00000000;
        }
        return ret;
    }

    function lpkDecrypt(key, data) {
        const ret = new Uint8Array(data.length);
        const slices = Math.ceil(data.length / 1024);

        for (let s = 0; s < slices; s++) {
            const start = s * 1024;
            const end = Math.min(start + 1024, data.length);
            let tmpKey = key >>> 0;

            for (let i = start; i < end; i++) {
                tmpKey = (2531011 + 214013 * tmpKey) >>> 16;
                tmpKey = tmpKey & 0xffff;
                ret[i] = (tmpKey & 0xff) ^ data[i];
            }
        }

        return ret;
    }

    function isEncryptedFilename(s) {
        return /^[0-9a-f]{32}\.bin3?$/.test(s);
    }

    function guessFileType(data) {
        const header = new Uint8Array(data.slice(0, 4));
        if (header[0] === 0x89 && header[1] === 0x50 && header[2] === 0x4e && header[3] === 0x47) {
            return { ext: 'png', mime: 'image/png' };
        }
        if (header[0] === 0xff && header[1] === 0xd8 && header[2] === 0xff) {
            return { ext: 'jpg', mime: 'image/jpeg' };
        }
        if (header[0] === 0x4d && header[1] === 0x4f && header[2] === 0x43 && header[3] === 0x33) {
            return { ext: 'moc3', mime: 'application/octet-stream' };
        }
        if (header[0] === 0x6d && header[1] === 0x6f && header[2] === 0x63) {
            return { ext: 'moc', mime: 'application/octet-stream' };
        }
        try {
            const str = new TextDecoder('utf-8').decode(data.slice(0, 100));
            JSON.parse(str);
            return { ext: 'json', mime: 'application/json' };
        } catch (e) {}
        return { ext: 'bin', mime: 'application/octet-stream' };
    }

    function arrayBufferToBase64(buffer) {
        const bytes = new Uint8Array(buffer);
        let binary = '';
        for (let i = 0; i < bytes.byteLength; i++) {
            binary += String.fromCharCode(bytes[i]);
        }
        return btoa(binary);
    }

    function updateProgress(text, percent) {
        if (_onProgress) {
            _onProgress(text, percent);
        }
    }

    function loadScripts() {
        const basePath = '/static/live2d/';
        const scripts = [
            { name: 'JSZip', src: '/static/live2d/js/jszip.min.js', check: () => typeof JSZip !== 'undefined' },
            { name: 'Live2D Core', src: basePath + 'live2dcubismcore.min.js', check: () => typeof Live2DCubismCore !== 'undefined' },
            { name: 'Live2D Cubism 2', src: basePath + 'live2d.min.js', check: () => typeof Live2D !== 'undefined' },
            { name: 'PIXI.js', src: basePath + 'pixi.min.js', check: () => typeof PIXI !== 'undefined' }
        ];

        let loaded = 0;
        const total = scripts.length + 1;
        let hasError = false;

        return new Promise((resolve, reject) => {
            function loadNext() {
                if (loaded >= scripts.length) {
                    if (typeof PIXI !== 'undefined') {
                        window.PIXI = PIXI;
                    }
                    const displayScript = document.createElement('script');
                    displayScript.src = basePath + 'pixi-live2d-display.min.js';
                    displayScript.onload = () => {
                        loaded++;
                        updateProgress('加载Live2D Display...', Math.round(10 + (loaded / total) * 25));
                        setTimeout(() => {
                            const hasPIXI = typeof PIXI !== 'undefined';
                            const hasLive2DModel = hasPIXI && PIXI.live2d && typeof PIXI.live2d.Live2DModel !== 'undefined';

                            if (hasPIXI && hasLive2DModel) {
                                resolve();
                            } else {
                                reject(new Error('Live2D Display加载失败'));
                            }
                        }, 300);
                    };
                    displayScript.onerror = () => {
                        if (hasError) return;
                        hasError = true;
                        reject(new Error('Live2D Display加载失败'));
                    };
                    displayScript.timeout = 15000;
                    document.head.appendChild(displayScript);
                    return;
                }

                const scriptInfo = scripts[loaded];
                if (scriptInfo.check()) {
                    loaded++;
                    const progress = Math.round(10 + (loaded / total) * 25);
                    updateProgress(`加载${scriptInfo.name}...`, progress);
                    loadNext();
                    return;
                }

                const script = document.createElement('script');
                script.src = scriptInfo.src;
                script.onload = () => {
                    if (hasError) return;
                    loaded++;
                    const progress = Math.round(10 + (loaded / total) * 25);
                    updateProgress(`加载${scriptInfo.name}...`, progress);
                    loadNext();
                };
                script.onerror = () => {
                    if (hasError) return;
                    hasError = true;
                    reject(new Error(`${scriptInfo.name}加载失败`));
                };
                script.timeout = 15000;
                document.head.appendChild(script);
            }

            loadNext();
        });
    }

    function downloadLPK(url) {
        return fetch(url)
            .then(response => {
                if (!response.ok) throw new Error('Network response was not ok');
                const total = response.headers.get('content-length');
                return new Promise((resolve, reject) => {
                    const reader = response.body.getReader();
                    let received = 0;
                    const chunks = [];

                    reader.read().then(function processChunk({ done, value }) {
                        if (done) {
                            const totalLen = chunks.reduce((acc, chunk) => acc + chunk.length, 0);
                            const result = new Uint8Array(totalLen);
                            let offset = 0;
                            for (const chunk of chunks) {
                                result.set(chunk, offset);
                                offset += chunk.length;
                            }
                            resolve(result.buffer);
                            return;
                        }

                        received += value.length;
                        chunks.push(value);
                        if (total) {
                            const percent = Math.round(35 + (received / total) * 25);
                            updateProgress('下载模型文件...', Math.min(percent, 55));
                        }

                        reader.read().then(processChunk);
                    }).catch(reject);
                });
            });
    }

    function decryptLPK(zip) {
        return md5Hash('config.mlve').then(configHash => {
            const zipFiles = Object.keys(zip.files);
            let configFilename = null;

            const hashedConfig = configHash + '.bin3';
            const hashedConfigNoExt = configHash;

            if (zipFiles.includes(hashedConfig)) {
                configFilename = hashedConfig;
            } else if (zipFiles.includes(hashedConfigNoExt)) {
                configFilename = hashedConfigNoExt;
            } else if (zipFiles.includes('config.mlve')) {
                configFilename = 'config.mlve';
            } else {
                const jsonFile = zipFiles.find(f => f.endsWith('.model3.json'));
                if (jsonFile) {
                    return extractPlainLPK(zip, { list: [{ costume: [{ path: jsonFile }] }] });
                }
            }

            if (!configFilename) {
                throw new Error('config.mlve not found in LPK');
            }

            return zip.file(configFilename).async('uint8array').then(configData => {
                let mlveConfig;

                try {
                    const configJson = new TextDecoder('utf-8').decode(configData);
                    mlveConfig = JSON.parse(configJson);
                } catch (e) {
                    throw new Error('Failed to parse config.mlve');
                }

                const lpkType = mlveConfig.type || 'STD2_0';
                const lpkId = mlveConfig.id || '';
                const encrypt = mlveConfig.encrypt !== 'false';

                if (!encrypt) {
                    return extractPlainLPK(zip, mlveConfig);
                }

                return decryptEncryptedLPK(zip, mlveConfig, lpkType, lpkId);
            });
        });
    }

    function extractPlainLPK(zip, mlveConfig) {
        const files = Object.keys(zip.files);
        const modelFile = files.find(f => f.endsWith('.model3.json'));

        if (!modelFile) {
            throw new Error('Model JSON file not found in LPK');
        }

        const modelPath = modelFile.substring(0, modelFile.lastIndexOf('/') + 1);

        return zip.file(modelFile).async('text').then(jsonStr => {
            const settings = JSON.parse(jsonStr);
            return Promise.resolve({ zip, settings, modelPath, decryptedFiles: null });
        });
    }

    function decryptEncryptedLPK(zip, mlveConfig, lpkType, lpkId) {
        const charaList = mlveConfig.list || [];
        if (charaList.length === 0) {
            throw new Error('No character found in LPK config');
        }

        const chara = charaList[0];
        const costumes = chara.costume || [];
        if (costumes.length === 0) {
            throw new Error('No costume found in LPK config');
        }

        const costume = costumes[0];
        const modelJsonPath = costume.path;

        if (!modelJsonPath) {
            throw new Error('No model path found in costume');
        }

        const decryptedFiles = {};

        function decryptFile(filename) {
            if (decryptedFiles[filename]) {
                return Promise.resolve(decryptedFiles[filename]);
            }

            const zipFiles = Object.keys(zip.files);
            let actualFilename = filename;

            if (!zipFiles.includes(filename)) {
                return md5Hash(filename).then(hash => {
                    const hashedName = hash + '.bin3';
                    if (zipFiles.includes(hashedName)) {
                        actualFilename = hashedName;
                    } else if (zipFiles.includes(hash)) {
                        actualFilename = hash;
                    } else {
                        return null;
                    }
                    return doDecrypt(filename, actualFilename);
                });
            }

            return doDecrypt(filename, actualFilename);
        }

        function doDecrypt(originalName, zipName) {
            return zip.file(zipName).async('uint8array').then(data => {
                let key;
                if (lpkType === 'STM_1_0') {
                    key = lpkGenKey(lpkId + (mlveConfig.fileId || '') + originalName + (mlveConfig.metaData || ''));
                } else {
                    key = lpkGenKey(lpkId + originalName);
                }

                const decrypted = lpkDecrypt(key, data);
                decryptedFiles[originalName] = decrypted;
                return decrypted;
            });
        }

        function collectFilesFromJson(obj, fileSet) {
            if (typeof obj === 'string') {
                if (isEncryptedFilename(obj)) {
                    fileSet.add(obj);
                }
            } else if (Array.isArray(obj)) {
                obj.forEach(item => collectFilesFromJson(item, fileSet));
            } else if (obj && typeof obj === 'object') {
                Object.values(obj).forEach(val => collectFilesFromJson(val, fileSet));
            }
        }

        function findModelPath(settings) {
            const refs = settings.FileReferences || settings.fileReferences || {};
            const mocFile = refs.Moc || refs.moc || '';
            if (mocFile) {
                const parts = mocFile.split('/');
                if (parts.length > 1) {
                    return parts.slice(0, -1).join('/') + '/';
                }
            }
            return '';
        }

        return decryptFile(modelJsonPath).then(modelData => {
            let settings;
            try {
                const jsonStr = new TextDecoder('utf-8').decode(modelData);
                settings = JSON.parse(jsonStr);
            } catch (e) {
                throw new Error('Failed to parse decrypted model JSON');
            }

            updateProgress('解密模型资源...', 65);

            const fileSet = new Set();
            collectFilesFromJson(settings, fileSet);

            const fileList = Array.from(fileSet);
            const totalFiles = fileList.length;
            let decryptCount = 0;

            const decryptNext = () => {
                if (decryptCount >= totalFiles) {
                    const modelPath = findModelPath(settings);

                    const renamedFiles = {};
                    let renameIdx = 0;
                    Object.keys(decryptedFiles).forEach(encName => {
                        const data = decryptedFiles[encName];
                        const fileType = guessFileType(data);

                        let realName = encName;
                        if (isEncryptedFilename(encName)) {
                            realName = 'file_' + renameIdx + '.' + fileType.ext;
                            renameIdx++;
                        }
                        renamedFiles[realName] = { data, type: fileType, encName };
                    });

                    return { settings, decryptedFiles, renamedFiles, modelPath };
                }

                const fileName = fileList[decryptCount];
                return decryptFile(fileName).then(() => {
                    decryptCount++;
                    const percent = Math.round(65 + (decryptCount / totalFiles) * 10);
                    updateProgress('解密模型资源...', Math.min(percent, 75));
                    return decryptNext();
                });
            };

            return decryptNext();
        });
    }

    function extractDecryptedResources(data) {
        if (data.zip && !data.decryptedFiles) {
            return extractPlainResources(data);
        }

        return extractDecryptedResourcesInternal(data);
    }

    function extractPlainResources(data) {
        const { zip, settings, modelPath } = data;

        updateProgress('读取模型配置...', 76);

        const blobUrls = {};
        const allFiles = new Set();

        const addFile = (path) => {
            if (path && typeof path === 'string') {
                allFiles.add(modelPath + path);
            }
        };

        const addFiles = (arr) => {
            if (Array.isArray(arr)) {
                arr.forEach(f => addFile(f));
            }
        };

        const refs = settings.FileReferences || settings.fileReferences || {};
        addFile(refs.Moc || refs.moc);
        addFile(refs.Physics || refs.physics);
        addFile(refs.Pose || refs.pose);
        addFile(refs.DisplayInfo || refs.displayInfo);
        addFiles(refs.Textures || refs.textures);

        const motions = refs.Motions || refs.motions || {};
        Object.values(motions).forEach(motionList => {
            if (Array.isArray(motionList)) {
                motionList.forEach(m => {
                    if (m.File || m.file) addFile(m.File || m.file);
                });
            }
        });

        const expressions = refs.Expressions || refs.expressions || [];
        expressions.forEach(e => {
            if (e.File || e.file) addFile(e.File || e.file);
        });

        const fileList = Array.from(allFiles);
        const totalFiles = fileList.length;
        let loaded = 0;

        const loadFile = (filePath) => {
            const file = zip.file(filePath);
            if (!file) return Promise.resolve();

            const relativePath = filePath.substring(modelPath.length);

            return file.async('blob').then(blob => {
                blobUrls[relativePath] = URL.createObjectURL(blob);
                loaded++;
                const percent = Math.round(76 + (loaded / totalFiles) * 4);
                updateProgress('提取模型资源...', Math.min(percent, 80));
            });
        };

        return Promise.all(fileList.map(loadFile)).then(() => {
            const newSettings = JSON.parse(JSON.stringify(settings));

            const replacePath = (obj, key) => {
                if (obj[key] && typeof obj[key] === 'string') {
                    if (blobUrls[obj[key]]) {
                        obj[key] = blobUrls[obj[key]];
                    }
                }
            };

            const replacePaths = (obj, key) => {
                if (obj[key] && Array.isArray(obj[key])) {
                    obj[key] = obj[key].map(p => blobUrls[p] || p);
                }
            };

            const newRefs = newSettings.FileReferences || newSettings.fileReferences || {};
            replacePath(newRefs, 'Moc');
            replacePath(newRefs, 'moc');
            replacePath(newRefs, 'Physics');
            replacePath(newRefs, 'physics');
            replacePath(newRefs, 'Pose');
            replacePath(newRefs, 'pose');
            replacePaths(newRefs, 'Textures');
            replacePaths(newRefs, 'textures');

            if (newRefs.Motions) {
                Object.keys(newRefs.Motions).forEach(group => {
                    newRefs.Motions[group] = newRefs.Motions[group].map(m => {
                        if (m.File && blobUrls[m.File]) {
                            return { ...m, File: blobUrls[m.File] };
                        }
                        return m;
                    });
                });
            }

            if (newRefs.Expressions) {
                newRefs.Expressions = newRefs.Expressions.map(e => {
                    if (e.File && blobUrls[e.File]) {
                        return { ...e, File: blobUrls[e.File] };
                    }
                    return e;
                });
            }

            const modelJsonStr = JSON.stringify(newSettings);
            const modelBlob = new Blob([modelJsonStr], { type: 'application/json' });
            const modelUrl = URL.createObjectURL(modelBlob);

            return { modelUrl, settings: newSettings, blobUrls };
        });
    }

    function extractDecryptedResourcesInternal(data) {
        const { settings, decryptedFiles, renamedFiles } = data;

        updateProgress('处理解密资源...', 76);

        const dataUrls = {};
        const nameMapping = {};

        Object.keys(renamedFiles).forEach(realName => {
            const { data: fileData, type, encName } = renamedFiles[realName];
            const base64 = arrayBufferToBase64(fileData);
            const dataUrl = `data:${type.mime};base64,${base64}`;
            dataUrls[realName] = dataUrl;
            nameMapping[encName] = realName;
        });

        const newSettings = JSON.parse(JSON.stringify(settings));

        function replaceEncryptedNames(obj) {
            if (typeof obj === 'string') {
                if (nameMapping[obj]) {
                    return nameMapping[obj];
                }
                return obj;
            }
            if (Array.isArray(obj)) {
                return obj.map(replaceEncryptedNames);
            }
            if (obj && typeof obj === 'object') {
                const result = {};
                Object.keys(obj).forEach(key => {
                    result[key] = replaceEncryptedNames(obj[key]);
                });
                return result;
            }
            return obj;
        }

        const replacedSettings = replaceEncryptedNames(newSettings);

        function replaceDataUrls(obj) {
            if (typeof obj === 'string') {
                if (dataUrls[obj]) {
                    return dataUrls[obj];
                }
                return obj;
            }
            if (Array.isArray(obj)) {
                return obj.map(replaceDataUrls);
            }
            if (obj && typeof obj === 'object') {
                const result = {};
                Object.keys(obj).forEach(key => {
                    result[key] = replaceDataUrls(obj[key]);
                });
                return result;
            }
            return obj;
        }

        const finalSettings = replaceDataUrls(replacedSettings);

        const modelJsonStr = JSON.stringify(finalSettings);
        const modelDataUrl = `data:application/json;base64,${btoa(unescape(encodeURIComponent(modelJsonStr)))}`;

        updateProgress('资源处理完成...', 79);

        return { modelUrl: modelDataUrl, settings: finalSettings, dataUrls };
    }

    function initModel(data) {
        return new Promise((resolve, reject) => {
            try {
                const wrapper = _container;
                const width = wrapper.clientWidth;
                const height = wrapper.clientHeight;

                updateProgress('创建PIXI应用...', 82);

                const app = new PIXI.Application({
                    view: _canvas,
                    width: width,
                    height: height,
                    transparent: true,
                    autoStart: true,
                    antialias: true,
                    resolution: window.devicePixelRatio || 1,
                });

                _app = app;

                updateProgress('加载Live2D模型...', 85);

                const modelOptions = {
                    autoInteract: false,
                };

                const Live2DModelClass = typeof Live2DModel !== 'undefined' ? Live2DModel : PIXI.live2d.Live2DModel;
                Live2DModelClass.from(data.modelUrl, modelOptions)
                    .then(model => {
                        updateProgress('调整模型位置...', 95);

                        // 保存模型原始尺寸（未缩放），后续每次 resize 都基于原始尺寸重新计算，
                        // 避免用已缩放的 model.width/height 再次套公式导致链式二次放大
                        _modelBaseW = model.width;
                        _modelBaseH = model.height;
                        const baseScale = Math.min(width / _modelBaseW, height / _modelBaseH) * 0.9;
                        model.scale.set(baseScale);
                        model.x = width / 2;
                        model.y = height / 2 + (_modelBaseH * baseScale * 0.1);
                        model.anchor.set(0.5, 0.5);

                        app.stage.addChild(model);
                        _model = model;

                        model.on('hit', (hitAreas) => {
                            console.log('[Hit 事件] 命中区域:', hitAreas);
                            // 读取模型实际定义的动作组
                            let availableGroups = [];
                            try {
                                const im = model.internalModel;
                                if (im && im.motionManager && im.motionManager.definitions) {
                                    availableGroups = Object.keys(im.motionManager.definitions);
                                }
                                if (im && im.settings && im.settings.motions) {
                                    availableGroups = Object.keys(im.settings.motions);
                                }
                            } catch (e) {}
                            console.log('[可用动作组]:', availableGroups);

                            hitAreas.forEach(area => {
                                const lowerArea = area.toLowerCase();
                                const motionCandidates = [
                                    'tap_' + lowerArea,
                                    'Tap' + area,
                                    'tap' + area,
                                    area,
                                    lowerArea,
                                    'Tap_' + area,
                                ];
                                // 加入可用动作组中包含 area 名字的项
                                availableGroups.forEach(g => {
                                    if (g.toLowerCase().indexOf(lowerArea) !== -1 || lowerArea.indexOf(g.toLowerCase()) !== -1) {
                                        if (motionCandidates.indexOf(g) === -1) {
                                            motionCandidates.push(g);
                                        }
                                    }
                                });

                                let played = false;
                                for (let i = 0; i < motionCandidates.length; i++) {
                                    try {
                                        if (availableGroups.length === 0 || availableGroups.indexOf(motionCandidates[i]) !== -1) {
                                            model.motion(motionCandidates[i]);
                                            played = true;
                                            console.log('[触发动作]:', motionCandidates[i]);
                                            break;
                                        }
                                    } catch (e) {}
                                }
                                // 如果精确匹配都失败，尝试调用所有可用动作组中的第一个
                                if (!played && availableGroups.length > 0) {
                                    try {
                                        model.motion(availableGroups[0]);
                                        played = true;
                                        console.log('[兜底触发第一个动作组]:', availableGroups[0]);
                                    } catch (e) {}
                                }
                                if (!played) {
                                    console.log('[动作未找到] 区域:', area, '尝试过:', motionCandidates);
                                }
                            });
                        });

                        function handleMove(e) {
                            if (!_model) return;
                            e.preventDefault();
                            const rect = _canvas.getBoundingClientRect();
                            let clientX, clientY;
                            if (e.touches && e.touches.length > 0) {
                                clientX = e.touches[0].clientX;
                                clientY = e.touches[0].clientY;
                            } else {
                                clientX = e.clientX;
                                clientY = e.clientY;
                            }
                            const x = (clientX - rect.left) / rect.width * width;
                            const y = (clientY - rect.top) / rect.height * height;
                            if (typeof _model.focus === 'function') {
                                _model.focus(x, y);
                            }
                        }

                        let _lastTapTime = 0;
                        function handleTap(e) {
                            if (!_model) return;
                            e.preventDefault();
                            const now = Date.now();
                            if (now - _lastTapTime < 300) {
                                return;
                            }
                            _lastTapTime = now;
                            const rect = _canvas.getBoundingClientRect();
                            let clientX, clientY;
                            if (e.touches && e.touches.length > 0) {
                                clientX = e.touches[0].clientX;
                                clientY = e.touches[0].clientY;
                            } else {
                                clientX = e.clientX;
                                clientY = e.clientY;
                            }
                            const x = (clientX - rect.left) / rect.width * width;
                            const y = (clientY - rect.top) / rect.height * height;
                            if (typeof _model.tap === 'function') {
                                _model.tap(x, y);
                            }
                        }

                        _canvas.addEventListener('mousemove', handleMove);
                        _canvas.addEventListener('touchmove', handleMove, { passive: false });
                        _canvas.addEventListener('mousedown', handleTap);
                        _canvas.addEventListener('touchstart', handleTap, { passive: false });

                        function syncLayout() {
                            if (!_app || !_model) return;
                            const w = wrapper.clientWidth;
                            const h = wrapper.clientHeight;
                            // 先同步画布 CSS 尺寸与渲染尺寸，避免 devicePixelRatio + resize
                            // 导致 canvas 元素与 PIXI renderer 不一致
                            if (_canvas) {
                                _canvas.style.width = w + 'px';
                                _canvas.style.height = h + 'px';
                            }
                            app.renderer.resize(w, h);
                            // 始终基于模型原始未缩放尺寸重新计算，
                            // 防止用已缩放的 _model.width / _model.height 递归套公式导致每次 resize 都放大
                            const s = Math.min(w / _modelBaseW, h / _modelBaseH) * 0.9;
                            _model.scale.set(s);
                            _model.x = w / 2;
                            _model.y = h / 2 + (_modelBaseH * s * 0.1);
                        }

                        _resizeListener = () => {
                            // 节流：避免 resize 高频触发（F12 打开/关闭会多次）造成抖动
                            if (_resizeTimer) clearTimeout(_resizeTimer);
                            _resizeTimer = setTimeout(syncLayout, 60);
                        };
                        window.addEventListener('resize', _resizeListener);

                        // 同时监听 wrapper 容器本身尺寸变化（例如布局动画、父级展开折叠）
                        if (typeof ResizeObserver !== 'undefined') {
                            _resizeObserver = new ResizeObserver(() => {
                                if (_resizeTimer) clearTimeout(_resizeTimer);
                                _resizeTimer = setTimeout(syncLayout, 60);
                            });
                            _resizeObserver.observe(wrapper);
                        }

                        // 清理
                        // （options 是外层 loadLPK 的参数，此处闭包未使用，留注释以免误导后续扩展）

                        updateProgress('准备完成...', 100);
                        resolve(model);
                    })
                    .catch(err => {
                        console.error('Live2D model load error:', err);
                        reject(err);
                    });

            } catch (e) {
                console.error('PIXI init error:', e);
                reject(e);
            }
        });
    }

    function loadLPK(lpkUrl, container, options) {
        _lpkUrl = lpkUrl;
        _onProgress = options && options.onProgress ? options.onProgress : null;

        if (typeof container === 'string') {
            _container = document.querySelector(container);
        } else {
            _container = container;
        }

        if (!_container) {
            return Promise.reject(new Error('Container not found'));
        }

        _canvas = _container.querySelector('canvas');
        if (!_canvas) {
            _canvas = document.createElement('canvas');
            _container.appendChild(_canvas);
        }

        updateProgress('加载依赖库...', 0);

        return loadScripts()
            .then(() => {
                updateProgress('下载模型文件...', 35);
                return downloadLPK(_lpkUrl);
            })
            .then(buffer => {
                updateProgress('解压中...', 58);
                return JSZip.loadAsync(buffer);
            })
            .then(zip => {
                updateProgress('解密模型文件...', 60);
                return decryptLPK(zip);
            })
            .then(data => {
                updateProgress('提取模型资源...', 75);
                return extractDecryptedResources(data);
            })
            .then(resources => {
                updateProgress('初始化渲染引擎...', 80);
                return initModel(resources);
            })
            .then(model => {
                return {
                    model: model,
                    app: _app,
                    destroy: function () {
                        if (_resizeObserver) {
                            try { _resizeObserver.disconnect(); } catch (e) {}
                            _resizeObserver = null;
                        }
                        if (_resizeListener) {
                            try { window.removeEventListener('resize', _resizeListener); } catch (e) {}
                            _resizeListener = null;
                        }
                        if (_resizeTimer) {
                            clearTimeout(_resizeTimer);
                            _resizeTimer = null;
                        }
                        if (_app) {
                            _app.destroy(true);
                            _app = null;
                        }
                        _model = null;
                        _canvas = null;
                        _container = null;
                        _modelBaseW = 0;
                        _modelBaseH = 0;
                    }
                };
            });
    }

    return {
        load: loadLPK
    };
})();
