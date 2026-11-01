var studio={image:null,original:null,box:null,history:[],busy:false,room:null};

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
            if(!d.rooms.length){status.className='vision-status warn';status.textContent=d.skipped.length&&kind!=='plan'?'На фото: '+d.skipped.join(', ')+' — такие помещения сайт пока не проектирует.':'Не удалось распознать комнаты. '+(d.notes||'Попробуйте фото чётче или введите размеры вручную.');return}
            var found=d.rooms.map(function(r){return{type:r.type,width:r.width,length:r.length,height:r.height,wishes:''}});
            rooms=kind==='plan'?found:rooms.concat(found).slice(0,6);
            if(kind!=='plan'&&found[0].height)document.getElementById('ceiling-height').value=found[0].height;
            renderRooms();
            var msg=(kind==='plan'?'✅ С плана распознано помещений: ':'✅ Добавлена комната: ')+found.map(function(r){return ROOM_TYPES[r.type]+' '+r.width+'×'+r.length+' м'}).join(', ')+'.';
            if(d.skipped.length)msg+=' Пропущено: '+d.skipped.join(', ')+'.';
            if(d.rooms.some(function(r){return r.typical}))msg+=' Размер по фото не определился — подставлен типичный для такой комнаты, поправьте вручную.';
            else if(d.estimate)msg+=' Размеры по фото примерные — проверьте рулеткой.';
            status.textContent=msg;
        }).catch(function(e){status.className='vision-status warn';status.textContent='⚠️ '+e.message});
    });
}

function studioOpen(i){
    var room=currentResult.rooms[i];
    if(!room||!room.image_url)return;
    studio.room=i;studio.image=studio.original=room.image_url;studio.history=[];studio.box=null;
    document.getElementById('studio-title').textContent='✏️ Правка фото: '+room.room_name;
    document.getElementById('studio').hidden=false;
    document.body.style.overflow='hidden';
    studioRender();studioSuggestions(null);
}

function studioClose(){
    if(studio.busy)return;
    if(studio.image!==studio.original&&!confirm('Закрыть без сохранения? Правки пропадут.'))return;
    document.getElementById('studio').hidden=true;
    document.body.style.overflow='';
}

function studioSave(){
    var i=studio.room,room=currentResult.rooms[i];
    studioBusy('💾 Сохраняю…');
    postJSON('/photo/save-room',{task_id:currentResult.task_id||null,room_index:i,image:studio.image}).then(function(){
        room.image_url=studio.image;room.edited=true;studio.original=studio.image;studio.history=[];
        studioBusy(null);studioRender();setPhotoState(i,'done');
        document.getElementById('studio').hidden=true;document.body.style.overflow='';
    }).catch(studioError);
}

function studioRender(){
    document.getElementById('studio-img').src=studio.image;
    document.getElementById('studio-before').src=studio.original;
    document.getElementById('studio-after').src=studio.image;
    document.getElementById('studio-undo').disabled=!studio.history.length;
    document.getElementById('studio-compare').hidden=studio.image===studio.original;
    document.getElementById('studio-save').disabled=studio.image===studio.original;
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
    postJSON('/photo/suggest',{image:studio.image,box:studio.box,style:studioStyle()})
        .then(function(d){studioBusy(null);studioDrawBox();studioSuggestions(d)}).catch(studioError);
}

function studioInpaint(prompt){
    if(!studio.box||!prompt)return;
    studioBusy('🎨 Перерисовываю выделенную область…');
    postJSON('/photo/inpaint',{image:studio.image,box:studio.box,prompt:prompt,style:studioStyle()})
        .then(studioPush).catch(studioError);
}

function studioApplySuggestion(i){studioInpaint(studio.suggestions[i].prompt)}
function studioApplyCustom(){studioInpaint(document.getElementById('studio-prompt').value.trim())}

function studioStyle(){return currentResult&&currentResult.style||'Современный'}

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
    if(!document.getElementById('studio-stage'))return;
    studioInitSelection();
    document.addEventListener('keydown',function(e){if(e.key==='Escape'&&!document.getElementById('studio').hidden)studioClose()});
});
