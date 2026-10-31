var studio={image:null,original:null,box:null,history:[],busy:false};

function readImageFile(file,maxSide){
    return new Promise(function(resolve,reject){
        if(!file||!/^image\//.test(file.type)){reject(new Error('Нужен файл изображения'));return}
        var reader=new FileReader();
        reader.onerror=function(){reject(new Error('Не удалось прочитать файл'))};
        reader.onload=function(){
            var img=new Image();
            img.onerror=function(){reject(new Error('Не удалось открыть изображение'))};
            img.onload=function(){
                var k=Math.min(1,maxSide/Math.max(img.width,img.height)),c=document.createElement('canvas');
                c.width=Math.round(img.width*k);c.height=Math.round(img.height*k);
                c.getContext('2d').drawImage(img,0,0,c.width,c.height);
                resolve(c.toDataURL('image/jpeg',0.92));
            };
            img.src=reader.result;
        };
        reader.readAsDataURL(file);
    });
}

function postJSON(url,body){
    return fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})
        .then(function(r){return r.json().then(function(d){if(!r.ok)throw new Error(apiError(d));return d})});
}

function pickFile(onFile){
    var input=document.createElement('input');input.type='file';input.accept='image/*';
    input.onchange=function(){if(input.files[0])onFile(input.files[0])};
    input.click();
}

function roomsFromImage(kind){
    pickFile(function(file){
        var status=document.getElementById('vision-status');
        status.hidden=false;status.className='vision-status';
        status.textContent=kind==='plan'?'🧠 Читаю план квартиры… (до минуты)':'🧠 Оцениваю комнату по фото… (до минуты)';
        readImageFile(file,1280).then(function(dataUrl){return postJSON('/vision/rooms',{image:dataUrl,kind:kind})}).then(function(d){
            if(!d.rooms.length){status.className='vision-status warn';status.textContent='Не удалось распознать комнаты. '+(d.notes||'Попробуйте фото чётче или введите размеры вручную.');return}
            var found=d.rooms.map(function(r){return{type:r.type,width:r.width,length:r.length,height:r.height,wishes:''}});
            rooms=kind==='plan'?found:rooms.concat(found).slice(0,6);
            if(kind!=='plan'&&found[0].height)document.getElementById('ceiling-height').value=found[0].height;
            renderRooms();
            var msg=(kind==='plan'?'✅ С плана распознано помещений: ':'✅ Добавлена комната: ')+found.map(function(r){return ROOM_TYPES[r.type]+' '+r.width+'×'+r.length+' м'}).join(', ')+'.';
            if(d.skipped.length)msg+=' Пропущено: '+d.skipped.join(', ')+'.';
            if(d.estimate)msg+=' Размеры по фото примерные — проверьте рулеткой.';
            status.textContent=msg;
        }).catch(function(e){status.className='vision-status warn';status.textContent='⚠️ '+e.message});
    });
}

function studioLoad(file){
    readImageFile(file,1280).then(function(dataUrl){
        studio.image=studio.original=dataUrl;studio.history=[];studio.box=null;
        document.getElementById('studio-drop').hidden=true;
        document.getElementById('studio-work').hidden=false;
        studioRender();studioSuggestions(null);
    }).catch(function(e){alert(e.message)});
}

function studioRender(){
    document.getElementById('studio-img').src=studio.image;
    document.getElementById('studio-before').src=studio.original;
    document.getElementById('studio-after').src=studio.image;
    document.getElementById('studio-undo').disabled=!studio.history.length;
    document.getElementById('studio-compare').hidden=studio.image===studio.original;
    studioDrawBox();
}

function studioDrawBox(){
    var sel=document.getElementById('studio-sel'),b=studio.box;
    sel.hidden=!b;
    if(b){sel.style.left=b.x*100+'%';sel.style.top=b.y*100+'%';sel.style.width=b.w*100+'%';sel.style.height=b.h*100+'%'}
    document.getElementById('studio-suggest').disabled=!b;
    document.getElementById('studio-apply').disabled=!b;
}

function studioInitSelection(){
    var stage=document.getElementById('studio-stage'),start=null;
    function point(e){
        var r=stage.getBoundingClientRect();
        return{x:Math.min(Math.max((e.clientX-r.left)/r.width,0),1),y:Math.min(Math.max((e.clientY-r.top)/r.height,0),1)};
    }
    stage.addEventListener('pointerdown',function(e){
        if(studio.busy)return;
        start=point(e);stage.setPointerCapture(e.pointerId);e.preventDefault();
    });
    stage.addEventListener('pointermove',function(e){
        if(!start)return;
        var p=point(e);
        studio.box={x:Math.min(start.x,p.x),y:Math.min(start.y,p.y),w:Math.abs(p.x-start.x),h:Math.abs(p.y-start.y)};
        studioDrawBox();
    });
    stage.addEventListener('pointerup',function(){
        start=null;
        if(studio.box&&(studio.box.w<0.03||studio.box.h<0.03))studio.box=null;
        studioDrawBox();
    });
}

function studioBusy(text){
    studio.busy=!!text;
    var s=document.getElementById('studio-status');s.hidden=!text;s.textContent=text||'';
    document.getElementById('studio-work').classList.toggle('busy',!!text);
}

function studioError(e){studioBusy(null);studioDrawBox();alert('⚠️ '+e.message)}

function studioSuggestions(d){
    var box=document.getElementById('studio-suggestions');
    if(!d){box.innerHTML='';return}
    box.innerHTML=(d.object?'<p class="order-note">В выделенной области: <b>'+esc(d.object)+'</b></p>':'')
        +d.suggestions.map(function(s,i){
            return'<div class="suggestion"><div><b>'+esc(s.title)+'</b><p>'+esc(s.description)+'</p></div><button type="button" class="btn-secondary" onclick="studioApplySuggestion('+i+')">Применить</button></div>';
        }).join('');
    studio.suggestions=d.suggestions;
}

function studioSuggest(){
    if(!studio.box)return;
    studioBusy('🧠 Смотрю на выделенную область… (до минуты)');
    postJSON('/photo/suggest',{image:studio.image,box:studio.box,style:document.getElementById('studio-style').value})
        .then(function(d){studioBusy(null);studioDrawBox();studioSuggestions(d)}).catch(studioError);
}

function studioInpaint(prompt){
    if(!studio.box||!prompt)return;
    studioBusy('🎨 Перерисовываю выделенную область…');
    postJSON('/photo/inpaint',{image:studio.image,box:studio.box,prompt:prompt,style:document.getElementById('studio-style').value})
        .then(studioPush).catch(studioError);
}

function studioApplySuggestion(i){studioInpaint(studio.suggestions[i].prompt)}
function studioApplyCustom(){studioInpaint(document.getElementById('studio-prompt').value.trim())}

function studioRestyle(){
    studioBusy('🪄 Перерисовываю всё фото… (до минуты)');
    postJSON('/photo/restyle',{
        image:studio.image,
        style:document.getElementById('studio-style').value,
        mode:document.getElementById('studio-mode').value,
        room_type:document.getElementById('studio-room').value,
        prompt:document.getElementById('studio-restyle-prompt').value.trim()
    }).then(studioPush).catch(studioError);
}

function studioPush(d){
    studio.history.push(studio.image);studio.image=d.image;studio.box=null;
    studioBusy(null);studioSuggestions(null);studioRender();
}

function studioUndo(){
    if(!studio.history.length)return;
    studio.image=studio.history.pop();studio.box=null;studioRender();
}

function studioDownload(){
    var a=document.createElement('a');a.href=studio.image;a.download='black-hole-photo_'+Date.now()+'.png';
    document.body.appendChild(a);a.click();document.body.removeChild(a);
}

function studioCompare(v){document.getElementById('studio-after-wrap').style.clipPath='inset(0 0 0 '+v+'%)'}

document.addEventListener('DOMContentLoaded',function(){
    var drop=document.getElementById('studio-drop');
    if(!drop)return;
    drop.addEventListener('click',function(){pickFile(studioLoad)});
    drop.addEventListener('dragover',function(e){e.preventDefault();drop.classList.add('over')});
    drop.addEventListener('dragleave',function(){drop.classList.remove('over')});
    drop.addEventListener('drop',function(e){e.preventDefault();drop.classList.remove('over');if(e.dataTransfer.files[0])studioLoad(e.dataTransfer.files[0])});
    studioInitSelection();
});
